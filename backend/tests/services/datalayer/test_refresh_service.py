from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from backend.resources.sleeper_data.league_seasons import RefreshSeasonIdentity
from backend.resources.sleeper_data.normalized_scopes import ApplyResult
from backend.resources.sleeper_data.refreshes import RefreshRun, StartRefresh
from backend.resources.sleeper_data.requests import (
    ApiRequest,
    NormalizationRejection,
    RecordApiAttempt,
)
from backend.services.datalayer import (
    ApplyDisposition,
    EndpointKind,
    LocalDatalayerFileStore,
    NormalizationStatus,
    RefreshRequest,
    RefreshStatus,
    RefreshTrigger,
    RequestStatus,
    ScopeKey,
    StoredLocalArtifact,
    SuccessfulSourceAttempt,
    build_league_request,
    normalize_league,
)
from backend.services.datalayer.canonical_json import canonical_json_bytes
from backend.services.datalayer.errors import DatalayerScopeConflict
from backend.services.datalayer.errors import RosterIdentityMappingRequired
from backend.services.datalayer.refresh_service import (
    DatalayerRefreshService,
    build_standard_refresh_plan,
)
from backend.services.datalayer.sleeper.responses import (
    EndpointRequest,
    FailedSourceAttempt,
    SanitizedSourceError,
    SourceAttempt,
)


NOW = datetime(2026, 8, 19, tzinfo=timezone.utc)
COMPETITION_ID = UUID("10000000-0000-0000-0000-000000000001")
SEASON_ID = UUID("20000000-0000-0000-0000-000000000002")
REFRESH_ID = UUID("30000000-0000-0000-0000-000000000003")
IDENTITY = RefreshSeasonIdentity(
    competition_id=COMPETITION_ID,
    competition_season_id=SEASON_ID,
    sleeper_league_id="league-1",
    season_year=2026,
)


def test_standard_plan_has_exact_dependency_order_and_conditionals() -> None:
    league_request = build_league_request(SEASON_ID, "league-1")
    league = normalize_league(
        _league_payload(playoff_week=2, draft_rounds=2), league_request
    )

    plan = build_standard_refresh_plan(
        IDENTITY,
        through_week=2,
        league_records=league,
    )

    assert [request.endpoint_kind for request in plan.requests] == [
        EndpointKind.LEAGUE,
        EndpointKind.LEAGUE_USERS,
        EndpointKind.NFL_STATE,
        EndpointKind.PLAYER_CATALOG,
        EndpointKind.LEAGUE_ROSTERS,
        EndpointKind.TRADED_PICKS,
        EndpointKind.MATCHUPS,
        EndpointKind.TRANSACTIONS,
        EndpointKind.MATCHUPS,
        EndpointKind.TRANSACTIONS,
        EndpointKind.WINNERS_BRACKET,
        EndpointKind.LOSERS_BRACKET,
    ]
    assert [request.week for request in plan.requests[6:10]] == [1, 1, 2, 2]
    roster = plan.endpoint_scope[4]
    assert roster.dependency_scope_keys == (
        ScopeKey.from_parts(EndpointKind.LEAGUE, SEASON_ID),
        ScopeKey.from_parts(EndpointKind.LEAGUE_USERS, SEASON_ID),
        ScopeKey.from_parts(EndpointKind.PLAYER_CATALOG, "nfl"),
    )


def test_standard_plan_omits_unresolved_week_and_league_conditionals() -> None:
    plan = build_standard_refresh_plan(
        IDENTITY,
        through_week=None,
        league_records=None,
    )

    assert [request.endpoint_kind for request in plan.requests] == [
        EndpointKind.LEAGUE,
        EndpointKind.LEAGUE_USERS,
        EndpointKind.NFL_STATE,
        EndpointKind.PLAYER_CATALOG,
        EndpointKind.LEAGUE_ROSTERS,
    ]


def test_refresh_without_week_does_not_guess_after_nfl_failure(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    source = FakeSource(
        permanent_failures={EndpointKind.NFL_STATE},
        payloads=_payloads(nfl_week=8, playoff_week=9),
    )

    outcome = _service(tmp_path, source, backend).refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=None,
            trigger=RefreshTrigger.MANUAL,
        )
    )

    assert outcome.status is RefreshStatus.PARTIAL
    assert outcome.effective_through_week is None
    assert outcome.requested_scope_count == 5
    assert all(
        not result.scope_key.value.startswith(("matchups:", "transactions:"))
        for result in outcome.scope_results
    )


def test_refresh_derives_week_retries_and_records_before_backoff(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    source = FakeSource(
        failures={EndpointKind.PLAYER_CATALOG: 1},
        payloads=_payloads(nfl_week=2, playoff_week=3),
    )
    delays: list[float] = []

    def delay(seconds: float) -> None:
        delays.append(seconds)
        assert any(
            item.endpoint_kind is EndpointKind.PLAYER_CATALOG
            for item in backend.requests
        )

    outcome = _service(tmp_path, source, backend, delay=delay).refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=None,
            trigger=RefreshTrigger.MANUAL,
        )
    )

    assert outcome.status is RefreshStatus.SUCCEEDED
    assert outcome.effective_through_week == 2
    assert outcome.requested_scope_count == 9
    assert outcome.failed_scope_count == 0
    assert delays == [0.5]
    assert [item.endpoint_kind for item in backend.requests].count(
        EndpointKind.PLAYER_CATALOG
    ) == 2
    assert [
        result.scope_key
        for result in outcome.scope_results
        if result.scope_key.value.startswith("matchups:")
    ] == [
        ScopeKey.from_parts(EndpointKind.MATCHUPS, SEASON_ID, 1),
        ScopeKey.from_parts(EndpointKind.MATCHUPS, SEASON_ID, 2),
    ]


def test_incomplete_payload_retries_with_backoff_and_applies_latest_attempt(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    source = FakeSource(
        payloads=_payloads(nfl_week=1, playoff_week=3),
        payload_sequences={
            EndpointKind.PLAYER_CATALOG: [
                {"p1": None},
                {"p1": None},
                {"p1": {"player_id": "p1"}},
            ]
        },
    )
    delays: list[float] = []

    outcome = _service(
        tmp_path, source, backend, delay=delays.append
    ).refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=1,
            trigger=RefreshTrigger.MANUAL,
        )
    )

    player_attempts = [
        item
        for item in backend.requests
        if item.endpoint_kind is EndpointKind.PLAYER_CATALOG
    ]
    assert outcome.effective_through_week == 1
    player_result = next(
        result
        for result in outcome.scope_results
        if result.scope_key
        == ScopeKey.from_parts(EndpointKind.PLAYER_CATALOG, "nfl")
    )
    assert delays == [0.5, 1.0]
    assert [item.is_complete for item in player_attempts] == [False, False, True]
    assert player_result.api_request_id == player_attempts[-1].id
    assert player_result.normalization_status is NormalizationStatus.SUCCEEDED


def test_retryable_source_failures_retry_but_permanent_http_does_not(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    source = FakeSource(
        payloads=_payloads(nfl_week=1, playoff_week=3),
        failure_scripts={
            EndpointKind.LEAGUE_USERS: [
                (RequestStatus.INVALID_PAYLOAD, 200)
            ],
            EndpointKind.PLAYER_CATALOG: [(RequestStatus.HTTP_ERROR, 429)],
            EndpointKind.LEAGUE_ROSTERS: [(RequestStatus.HTTP_ERROR, 503)],
            EndpointKind.NFL_STATE: [(RequestStatus.HTTP_ERROR, 404)],
        },
    )
    delays: list[float] = []

    outcome = _service(
        tmp_path, source, backend, delay=delays.append
    ).refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=1,
            trigger=RefreshTrigger.MANUAL,
        )
    )

    assert outcome.status is RefreshStatus.PARTIAL
    assert delays == [0.5, 0.5, 0.5]
    assert source.call_kinds.count(EndpointKind.NFL_STATE) == 1
    assert source.call_kinds.count(EndpointKind.LEAGUE_USERS) == 2
    assert source.call_kinds.count(EndpointKind.PLAYER_CATALOG) == 2
    assert source.call_kinds.count(EndpointKind.LEAGUE_ROSTERS) == 2


def test_explicit_week_wins_when_nfl_state_fails(tmp_path: Path) -> None:
    backend = FakeBackend()
    source = FakeSource(
        permanent_failures={EndpointKind.NFL_STATE},
        payloads=_payloads(nfl_week=8, playoff_week=9),
    )

    outcome = _service(tmp_path, source, backend).refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=1,
            trigger=RefreshTrigger.BACKFILL,
        )
    )

    assert outcome.status is RefreshStatus.PARTIAL
    assert any(
        result.scope_key == ScopeKey.from_parts(EndpointKind.MATCHUPS, SEASON_ID, 1)
        and result.normalization_status is NormalizationStatus.SUCCEEDED
        for result in outcome.scope_results
    )
    nfl = next(
        result
        for result in outcome.scope_results
        if result.scope_key == ScopeKey.from_parts(EndpointKind.NFL_STATE, "nfl")
    )
    assert nfl.fetch_status is RequestStatus.HTTP_ERROR
    assert nfl.warning_codes == ("sleeper_http_error",)


def test_missing_dependency_rejects_downstream_scopes(tmp_path: Path) -> None:
    backend = FakeBackend()
    source = FakeSource(
        permanent_failures={EndpointKind.PLAYER_CATALOG},
        payloads=_payloads(nfl_week=1, playoff_week=3),
    )

    outcome = _service(tmp_path, source, backend).refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=1,
            trigger=RefreshTrigger.SCHEDULED,
        )
    )

    roster = next(
        result
        for result in outcome.scope_results
        if result.scope_key
        == ScopeKey.from_parts(EndpointKind.LEAGUE_ROSTERS, SEASON_ID)
    )
    matchup = next(
        result
        for result in outcome.scope_results
        if result.scope_key == ScopeKey.from_parts(EndpointKind.MATCHUPS, SEASON_ID, 1)
    )
    assert outcome.status is RefreshStatus.PARTIAL
    assert roster.normalization_status is NormalizationStatus.REJECTED
    assert roster.warning_codes == ("normalization_dependency_unavailable",)
    assert matchup.normalization_status is NormalizationStatus.REJECTED


def test_scope_mapping_conflict_becomes_structured_rejection(
    tmp_path: Path,
) -> None:
    backend = FakeBackend(conflict_endpoint_kind=EndpointKind.TRANSACTIONS)
    source = FakeSource(payloads=_payloads(nfl_week=1, playoff_week=3))

    outcome = _service(tmp_path, source, backend).refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=1,
            trigger=RefreshTrigger.MANUAL,
        )
    )

    transaction = next(
        result
        for result in outcome.scope_results
        if result.scope_key
        == ScopeKey.from_parts(EndpointKind.TRANSACTIONS, SEASON_ID, 1)
    )
    assert outcome.status is RefreshStatus.PARTIAL
    assert transaction.normalization_status is NormalizationStatus.REJECTED
    assert transaction.warning_codes == ("normalization_scope_conflict",)


def test_large_payload_storage_failure_falls_back_to_inline(tmp_path: Path) -> None:
    backend = FakeBackend()
    source = FakeSource(payloads=_payloads(nfl_week=1, playoff_week=3))

    outcome = _service(
        tmp_path,
        source,
        backend,
        files=FailingFileStore(),
        inline_payload_max_bytes=1,
    ).refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=1,
            trigger=RefreshTrigger.GENERATION,
        )
    )

    assert outcome.status is RefreshStatus.SUCCEEDED
    assert all(
        "payload_storage_fallback" in result.warning_codes
        for result in outcome.scope_results
    )
    assert all(command.object_receipt is None for command in backend.commands)


def test_large_payloads_are_recorded_with_object_receipts(tmp_path: Path) -> None:
    backend = FakeBackend()
    source = FakeSource(payloads=_payloads(nfl_week=1, playoff_week=3))

    outcome = _service(
        tmp_path,
        source,
        backend,
        inline_payload_max_bytes=1,
    ).refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=1,
            trigger=RefreshTrigger.MANUAL,
        )
    )

    assert outcome.status is RefreshStatus.SUCCEEDED
    assert all(command.object_receipt is not None for command in backend.commands)


def test_refresh_bootstraps_first_season_before_roster_projection(
    tmp_path: Path,
) -> None:
    backend = FakeBackend()
    mapper = FakeRosterMapper()
    payloads = _payloads(nfl_week=1, playoff_week=3)
    payloads[EndpointKind.LEAGUE_ROSTERS] = [
        {"roster_id": 1, "settings": {}, "metadata": {}}
    ]
    source = FakeSource(payloads=payloads)

    outcome = _service(
        tmp_path,
        source,
        backend,
        roster_mappings=mapper,
    ).refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=1,
            trigger=RefreshTrigger.MANUAL,
        )
    )

    assert outcome.status is RefreshStatus.SUCCEEDED
    assert mapper.calls == [(SEASON_ID, 1, 0)]


def test_missing_later_season_mapping_has_actionable_warning(tmp_path: Path) -> None:
    backend = FakeBackend(
        mapping_required_endpoint_kind=EndpointKind.LEAGUE_ROSTERS
    )
    source = FakeSource(payloads=_payloads(nfl_week=1, playoff_week=3))

    outcome = _service(tmp_path, source, backend).refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=1,
            trigger=RefreshTrigger.MANUAL,
        )
    )

    roster_result = next(
        row
        for row in outcome.scope_results
        if row.scope_key.value.startswith("league_rosters:")
    )
    assert roster_result.warning_codes == ("roster_identity_mapping_required",)
    assert all(
        command.object_receipt.storage_key.startswith("payloads/sha256/")
        for command in backend.commands
        if command.object_receipt is not None
    )


class FailingFileStore:
    def store_bytes(
        self, kind: Any, content: bytes
    ) -> StoredLocalArtifact:
        del kind, content
        raise OSError("object store unavailable")


class FakeIdentityReader:
    def get_refresh_identity(
        self, competition_season_id: UUID
    ) -> RefreshSeasonIdentity:
        assert competition_season_id == SEASON_ID
        return IDENTITY


class FakeSource:
    def __init__(
        self,
        *,
        payloads: dict[EndpointKind, Any],
        failures: dict[EndpointKind, int] | None = None,
        permanent_failures: set[EndpointKind] | None = None,
        payload_sequences: dict[EndpointKind, list[Any]] | None = None,
        failure_scripts: dict[
            EndpointKind, list[tuple[RequestStatus, int | None]]
        ]
        | None = None,
    ) -> None:
        self.payloads = payloads
        self.failures = dict(failures or {})
        self.permanent_failures = permanent_failures or set()
        self.payload_sequences = {
            key: list(values) for key, values in (payload_sequences or {}).items()
        }
        self.failure_scripts = {
            key: list(values) for key, values in (failure_scripts or {}).items()
        }
        self.call_kinds: list[EndpointKind] = []

    def execute(self, request: EndpointRequest) -> SourceAttempt:
        self.call_kinds.append(request.endpoint_kind)
        scripted_failures = self.failure_scripts.get(request.endpoint_kind, [])
        if scripted_failures:
            status, http_status = scripted_failures.pop(0)
            return _failed(request, status=status, http_status=http_status)
        remaining = self.failures.get(request.endpoint_kind, 0)
        if remaining:
            self.failures[request.endpoint_kind] = remaining - 1
            return _failed(request, status=RequestStatus.TRANSPORT_ERROR)
        if request.endpoint_kind in self.permanent_failures:
            return _failed(
                request,
                status=RequestStatus.HTTP_ERROR,
                http_status=404,
            )
        sequence = self.payload_sequences.get(request.endpoint_kind, [])
        payload = sequence.pop(0) if sequence else self.payloads[request.endpoint_kind]
        return _successful(request, payload)


class FakeBackend:
    def __init__(
        self,
        *,
        conflict_endpoint_kind: EndpointKind | None = None,
        mapping_required_endpoint_kind: EndpointKind | None = None,
    ) -> None:
        self.command: StartRefresh | None = None
        self.requests: list[ApiRequest] = []
        self.commands: list[RecordApiAttempt] = []
        self.conflict_endpoint_kind = conflict_endpoint_kind
        self.mapping_required_endpoint_kind = mapping_required_endpoint_kind

    def start_refresh(self, command: StartRefresh) -> RefreshRun:
        self.command = command
        return self._refresh(RefreshStatus.RUNNING, 0, 0)

    def finish_refresh(self, refresh_id: UUID) -> RefreshRun:
        assert refresh_id == REFRESH_ID
        assert self.command is not None
        latest = {item.scope_key: item for item in self.requests}
        succeeded = sum(
            latest[item.scope_key].normalization_status
            is NormalizationStatus.SUCCEEDED
            for item in self.command.endpoint_scope
        )
        failed = len(self.command.endpoint_scope) - succeeded
        status = (
            RefreshStatus.SUCCEEDED
            if failed == 0
            else RefreshStatus.PARTIAL
            if succeeded
            else RefreshStatus.FAILED
        )
        return self._refresh(status, succeeded, failed)

    def record_attempt(self, command: RecordApiAttempt) -> ApiRequest:
        self.commands.append(command)
        source = command.attempt
        successful = isinstance(source, SuccessfulSourceAttempt)
        request = ApiRequest(
            id=uuid4(),
            refresh_run_id=REFRESH_ID,
            competition_season_id=(
                None
                if source.endpoint.endpoint_kind
                in {EndpointKind.NFL_STATE, EndpointKind.PLAYER_CATALOG}
                else SEASON_ID
            ),
            endpoint_kind=source.endpoint.endpoint_kind,
            scope_key=source.endpoint.scope_key,
            request_path=source.endpoint.path,
            request_parameters=dict(source.endpoint.parameters),
            week=source.endpoint.week,
            bracket_kind=source.endpoint.bracket_kind,
            requested_at=source.requested_at,
            completed_at=source.completed_at,
            latency_ms=source.latency_ms,
            status=RequestStatus.SUCCEEDED if successful else source.status,
            http_status=source.http_status,
            error=None if successful else source.error.model_dump(mode="json"),
            is_complete=command.completeness.is_complete,
            completeness_reason=command.completeness.reason,
            payload_id=uuid4() if successful else None,
            response_sha256=source.raw_sha256 if successful else None,
            normalization_status=(
                NormalizationStatus.PENDING
                if successful and command.completeness.is_complete
                else NormalizationStatus.REJECTED
                if successful
                else NormalizationStatus.NOT_APPLICABLE
            ),
            normalizer_version=None,
            normalized_at=None,
        )
        self.requests.append(request)
        return request

    def reject_normalization(
        self, request_id: UUID, rejection: NormalizationRejection
    ) -> ApiRequest:
        del rejection
        request = self._request(request_id).model_copy(
            update={"normalization_status": NormalizationStatus.REJECTED}
        )
        self._replace(request)
        return request

    def apply_scope(self, request_id: UUID, records: Any) -> ApplyResult:
        del records
        current = self._request(request_id)
        if current.endpoint_kind is self.mapping_required_endpoint_kind:
            raise RosterIdentityMappingRequired("mapping required")
        if current.endpoint_kind is self.conflict_endpoint_kind:
            raise DatalayerScopeConflict("test mapping conflict")
        request = current.model_copy(
            update={"normalization_status": NormalizationStatus.SUCCEEDED}
        )
        self._replace(request)
        return ApplyResult(
            request_id=request.id,
            scope_key=request.scope_key,
            disposition=ApplyDisposition.APPLIED,
            head_request_id=request.id,
            normalized_row_count=1,
            changed_current_view=True,
        )

    def _request(self, request_id: UUID) -> ApiRequest:
        return next(item for item in self.requests if item.id == request_id)

    def _replace(self, replacement: ApiRequest) -> None:
        self.requests = [
            replacement if item.id == replacement.id else item
            for item in self.requests
        ]

    def _refresh(
        self,
        status: RefreshStatus,
        succeeded: int,
        failed: int,
    ) -> RefreshRun:
        return RefreshRun(
            id=REFRESH_ID,
            competition_id=COMPETITION_ID,
            competition_season_id=SEASON_ID,
            requested_through_week=(
                None if self.command is None else self.command.requested_through_week
            ),
            endpoint_scope=() if self.command is None else self.command.endpoint_scope,
            trigger=(
                RefreshTrigger.MANUAL if self.command is None else self.command.trigger
            ),
            status=status,
            code_version="test",
            normalizer_version="1",
            started_at=NOW,
            completed_at=None if status is RefreshStatus.RUNNING else NOW,
            error=None,
            request_count=(
                0 if self.command is None else len(self.command.endpoint_scope)
            ),
            succeeded_request_count=succeeded,
            failed_request_count=failed,
        )


def _service(
    tmp_path: Path,
    source: FakeSource,
    backend: FakeBackend,
    *,
    delay: Any = lambda _: None,
    files: Any | None = None,
    inline_payload_max_bytes: int = 1024 * 1024,
    roster_mappings: Any | None = None,
) -> DatalayerRefreshService:
    return DatalayerRefreshService(
        source=source,
        identities=FakeIdentityReader(),
        refreshes=backend,
        attempts=backend,
        scopes=backend,
        files=files or LocalDatalayerFileStore(tmp_path),
        code_version="test",
        max_attempts=3,
        retry_backoff_seconds=0.5,
        inline_payload_max_bytes=inline_payload_max_bytes,
        delay=delay,
        roster_mappings=roster_mappings,
    )


class FakeRosterMapper:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, int, int]] = []

    def bootstrap_first_season(self, competition_season_id, rosters, users) -> None:
        self.calls.append(
            (
                competition_season_id,
                len(rosters.rosters),
                0 if users is None else len(users.users),
            )
        )


def _payloads(*, nfl_week: int, playoff_week: int) -> dict[EndpointKind, Any]:
    return {
        EndpointKind.LEAGUE: _league_payload(
            playoff_week=playoff_week, draft_rounds=0
        ),
        EndpointKind.LEAGUE_USERS: [],
        EndpointKind.NFL_STATE: {"season": "2026", "week": nfl_week},
        EndpointKind.PLAYER_CATALOG: {"p1": {"player_id": "p1"}},
        EndpointKind.LEAGUE_ROSTERS: [],
        EndpointKind.TRADED_PICKS: [],
        EndpointKind.MATCHUPS: [],
        EndpointKind.TRANSACTIONS: [],
        EndpointKind.WINNERS_BRACKET: [],
        EndpointKind.LOSERS_BRACKET: [],
    }


def _league_payload(*, playoff_week: int, draft_rounds: int) -> dict[str, Any]:
    return {
        "league_id": "league-1",
        "name": "Test League",
        "season": "2026",
        "sport": "nfl",
        "settings": {
            "playoff_week_start": playoff_week,
            "draft_rounds": draft_rounds,
        },
        "scoring_settings": {},
        "roster_positions": ["QB"],
    }


def _successful(request: EndpointRequest, payload: Any) -> SuccessfulSourceAttempt:
    content = canonical_json_bytes(payload)
    return SuccessfulSourceAttempt(
        endpoint=request,
        requested_at=NOW,
        completed_at=NOW,
        http_status=200,
        latency_ms=1,
        payload=payload,
        raw_sha256=hashlib.sha256(content).hexdigest(),
        byte_length=len(content),
        media_type="application/json",
    )


def _failed(
    request: EndpointRequest,
    *,
    status: RequestStatus,
    http_status: int | None = None,
) -> FailedSourceAttempt:
    return FailedSourceAttempt(
        endpoint=request,
        requested_at=NOW,
        completed_at=NOW,
        status=status,
        http_status=http_status,
        latency_ms=1,
        error=SanitizedSourceError(
            code=(
                "sleeper_http_error"
                if status is RequestStatus.HTTP_ERROR
                else "sleeper_invalid_json"
                if status is RequestStatus.INVALID_PAYLOAD
                else "sleeper_transport_error"
            ),
            summary="Source failed",
        ),
    )
