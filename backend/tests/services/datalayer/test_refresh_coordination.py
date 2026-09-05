from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from backend.resources.sleeper_data.league_seasons import SnapshotSeasonIdentity
from backend.resources.sleeper_data.refreshes import (
    AutomaticRefreshClaim,
    AutomaticRefreshClaimStatus,
    AutomaticRefreshFailure,
    ClaimedAutomaticRefresh,
    ExistingAutomaticRefresh,
    RefreshNeedReason,
)
from backend.services.datalayer.contracts import (
    RefreshOutcome,
    RefreshRequest,
    RefreshStatus,
    RefreshTrigger,
)
from backend.services.datalayer.errors import RefreshUnavailable
from backend.services.datalayer.refresh_coordination import (
    RefreshCoordinator,
    RefreshReceiptDisposition,
    automatic_refresh_active_key,
)
from backend.services.datalayer.snapshot_inputs import RefreshSeason


NOW = datetime(2026, 8, 25, 20, 0, tzinfo=timezone.utc)
SEASON_ID = UUID("10000000-0000-0000-0000-000000000001")
COMPETITION_ID = UUID("20000000-0000-0000-0000-000000000001")
HASH = "a" * 64


def _need() -> RefreshSeason:
    return RefreshSeason(
        season=SnapshotSeasonIdentity(
            competition_id=COMPETITION_ID,
            competition_season_id=SEASON_ID,
            sleeper_league_id="league-1",
            season_year=2026,
            sequence_number=1,
        ),
        through_week=8,
        reason=RefreshNeedReason.MISSING,
        coverage_fingerprint=HASH,
    )


def _claim(*, status: AutomaticRefreshClaimStatus) -> AutomaticRefreshClaim:
    terminal = status is not AutomaticRefreshClaimStatus.RUNNING
    completed = status is AutomaticRefreshClaimStatus.COMPLETED
    return AutomaticRefreshClaim(
        id=UUID("30000000-0000-0000-0000-000000000001"),
        competition_id=COMPETITION_ID,
        competition_season_id=SEASON_ID,
        active_key=automatic_refresh_active_key(_need()),
        requested_through_week=8,
        policy_version="multi-season-preparation-v1",
        reason=RefreshNeedReason.MISSING,
        coverage_fingerprint=HASH,
        status=status,
        refresh_run_id=(
            UUID("40000000-0000-0000-0000-000000000001") if completed else None
        ),
        refresh_status=RefreshStatus.PARTIAL if completed else None,
        failure=(
            AutomaticRefreshFailure(code="failed", summary="Refresh failed")
            if status is AutomaticRefreshClaimStatus.FAILED
            else None
        ),
        started_at=NOW,
        completed_at=NOW if terminal else None,
    )


class _Claims:
    def __init__(self, states: list[object], gets: list[AutomaticRefreshClaim] = ()):
        self.states = list(states)
        self.gets = list(gets)
        self.completed: list[tuple[UUID, object]] = []
        self.failures: list[tuple[UUID, object]] = []
        self.stale_results: list[bool] = []

    def begin_or_get(self, command: object) -> object:
        self.command = command
        return self.states.pop(0)

    def complete(self, claim_id: UUID, command: object) -> AutomaticRefreshClaim:
        self.completed.append((claim_id, command))
        return _claim(status=AutomaticRefreshClaimStatus.COMPLETED)

    def fail(self, claim_id: UUID, failure: object) -> AutomaticRefreshClaim:
        self.failures.append((claim_id, failure))
        return _claim(status=AutomaticRefreshClaimStatus.FAILED)

    def fail_stale(self, active_key: str, stale_before: datetime) -> bool:
        return self.stale_results.pop(0) if self.stale_results else False

    def get(self, claim_id: UUID) -> AutomaticRefreshClaim:
        return self.gets.pop(0) if len(self.gets) > 1 else self.gets[0]


class _Refreshes:
    def __init__(self, outcome: RefreshOutcome | Exception):
        self.outcome = outcome
        self.requests: list[RefreshRequest] = []

    def refresh(self, request: RefreshRequest) -> RefreshOutcome:
        self.requests.append(request)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _outcome(status: RefreshStatus = RefreshStatus.PARTIAL) -> RefreshOutcome:
    return RefreshOutcome(
        refresh_run_id=UUID("40000000-0000-0000-0000-000000000001"),
        status=status,
        effective_through_week=8,
        requested_scope_count=3,
        succeeded_scope_count=2,
        failed_scope_count=1,
        scope_results=(),
    )


def test_winner_runs_full_generation_refresh_and_persists_terminal_receipt() -> None:
    running = _claim(status=AutomaticRefreshClaimStatus.RUNNING)
    claims = _Claims([ClaimedAutomaticRefresh(claim=running)])
    refreshes = _Refreshes(_outcome())

    receipt = RefreshCoordinator(claims=claims, refreshes=refreshes).ensure(_need())

    assert refreshes.requests == [
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=8,
            trigger=RefreshTrigger.GENERATION,
        )
    ]
    assert receipt.status is RefreshStatus.PARTIAL
    assert receipt.disposition is RefreshReceiptDisposition.CLAIMED
    assert claims.completed[0][0] == running.id


def test_joiner_observes_terminal_receipt_without_running_refresh() -> None:
    running = _claim(status=AutomaticRefreshClaimStatus.RUNNING)
    complete = _claim(status=AutomaticRefreshClaimStatus.COMPLETED)
    claims = _Claims(
        [ExistingAutomaticRefresh(claim=running)],
        [running, complete],
    )
    refreshes = _Refreshes(_outcome())

    receipt = RefreshCoordinator(
        claims=claims,
        refreshes=refreshes,
        delay=lambda _: None,
    ).ensure(_need())

    assert receipt.disposition is RefreshReceiptDisposition.JOINED
    assert receipt.refresh_run_id == complete.refresh_run_id
    assert refreshes.requests == []


def test_one_stale_claim_is_recovered_and_reclaimed() -> None:
    running = _claim(status=AutomaticRefreshClaimStatus.RUNNING)
    claims = _Claims(
        [
            ExistingAutomaticRefresh(claim=running),
            ClaimedAutomaticRefresh(claim=running),
        ],
        [running],
    )
    claims.stale_results = [True]

    receipt = RefreshCoordinator(
        claims=claims,
        refreshes=_Refreshes(_outcome(RefreshStatus.SUCCEEDED)),
    ).ensure(_need())

    assert receipt.status is RefreshStatus.SUCCEEDED
    assert receipt.disposition is RefreshReceiptDisposition.CLAIMED


def test_operational_refresh_failure_is_sanitized_and_identified() -> None:
    running = _claim(status=AutomaticRefreshClaimStatus.RUNNING)
    claims = _Claims([ClaimedAutomaticRefresh(claim=running)])

    with pytest.raises(RefreshUnavailable) as caught:
        RefreshCoordinator(
            claims=claims,
            refreshes=_Refreshes(RuntimeError("secret source failure")),
        ).ensure(_need())

    assert caught.value.competition_season_id == SEASON_ID
    assert caught.value.claim_id == running.id
    assert "secret" not in str(caught.value)
    assert claims.failures


def test_join_timeout_is_retryable_and_keeps_claim_identifier() -> None:
    running = _claim(status=AutomaticRefreshClaimStatus.RUNNING)
    claims = _Claims([ExistingAutomaticRefresh(claim=running)], [running])
    ticks = iter((0.0, 31.0))

    with pytest.raises(RefreshUnavailable) as caught:
        RefreshCoordinator(
            claims=claims,
            refreshes=_Refreshes(_outcome()),
            monotonic_clock=lambda: next(ticks),
            delay=lambda _: None,
        ).ensure(_need())

    assert caught.value.claim_id == running.id
    assert caught.value.retryable is True


def test_active_key_changes_with_each_claim_identity_component() -> None:
    need = _need()
    changed = need.model_copy(update={"through_week": 9})

    assert automatic_refresh_active_key(need) == automatic_refresh_active_key(need)
    assert automatic_refresh_active_key(need) != automatic_refresh_active_key(changed)
    assert automatic_refresh_active_key(
        need, policy_version="next-policy"
    ) != automatic_refresh_active_key(need)
