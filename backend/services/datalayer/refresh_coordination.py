"""Claim, join, and recover one automatic full-season refresh."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import math
from time import monotonic, sleep
from typing import Protocol, assert_never
from uuid import UUID

from pydantic import Field

from backend.resources._contracts import ContractModel
from backend.resources.sleeper_data.refreshes import (
    AutomaticRefreshClaim,
    AutomaticRefreshClaimState,
    AutomaticRefreshClaimStatus,
    AutomaticRefreshFailure,
    ClaimAutomaticRefresh,
    ClaimedAutomaticRefresh,
    CompleteAutomaticRefresh,
    ExistingAutomaticRefresh,
)
from backend.services.datalayer.canonical_json import canonical_json_sha256
from backend.services.datalayer.contracts import (
    RefreshOutcome,
    RefreshRequest,
    RefreshStatus,
    RefreshTrigger,
)
from backend.services.datalayer.errors import RefreshUnavailable
from backend.services.datalayer.snapshot_inputs import RefreshSeason


AUTOMATIC_REFRESH_POLICY_VERSION = "multi-season-preparation-v1"
WallClock = Callable[[], datetime]
MonotonicClock = Callable[[], float]


class RefreshReceiptDisposition(StrEnum):
    CLAIMED = "claimed"
    JOINED = "joined"


class RefreshReceipt(ContractModel):
    claim_id: UUID
    competition_season_id: UUID
    through_week: int = Field(strict=True, ge=1, le=18)
    refresh_run_id: UUID
    status: RefreshStatus
    disposition: RefreshReceiptDisposition


class AutomaticRefreshClaims(Protocol):
    def begin_or_get(
        self,
        command: ClaimAutomaticRefresh,
    ) -> AutomaticRefreshClaimState: ...

    def complete(
        self,
        claim_id: UUID,
        command: CompleteAutomaticRefresh,
    ) -> AutomaticRefreshClaim: ...

    def fail(
        self,
        claim_id: UUID,
        failure: AutomaticRefreshFailure,
    ) -> AutomaticRefreshClaim: ...

    def fail_stale(self, active_key: str, stale_before: datetime) -> bool: ...

    def get(self, claim_id: UUID) -> AutomaticRefreshClaim: ...


class SeasonRefreshExecutor(Protocol):
    def refresh(self, request: RefreshRequest) -> RefreshOutcome: ...


class RefreshCoordinator:
    """Coalesce equivalent automatic work and retain its stable receipt."""

    def __init__(
        self,
        *,
        claims: AutomaticRefreshClaims,
        refreshes: SeasonRefreshExecutor,
        policy_version: str = AUTOMATIC_REFRESH_POLICY_VERSION,
        wait_timeout_seconds: float = 30.0,
        stale_after_seconds: float = 300.0,
        poll_interval_seconds: float = 0.1,
        clock: WallClock | None = None,
        monotonic_clock: MonotonicClock = monotonic,
        delay: Callable[[float], None] = sleep,
    ) -> None:
        if not policy_version.strip() or policy_version != policy_version.strip():
            raise ValueError("policy_version must not be empty")
        self._wait_timeout = _positive_number(
            wait_timeout_seconds, "wait_timeout_seconds"
        )
        self._stale_after = _positive_number(
            stale_after_seconds, "stale_after_seconds"
        )
        self._poll_interval = _positive_number(
            poll_interval_seconds, "poll_interval_seconds"
        )
        self._claims = claims
        self._refreshes = refreshes
        self._policy_version = policy_version
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic_clock
        self._delay = delay

    def ensure(self, need: RefreshSeason) -> RefreshReceipt:
        command = ClaimAutomaticRefresh(
            competition_season_id=need.season.competition_season_id,
            active_key=automatic_refresh_active_key(
                need,
                policy_version=self._policy_version,
            ),
            requested_through_week=need.through_week,
            policy_version=self._policy_version,
            reason=need.reason,
            coverage_fingerprint=need.coverage_fingerprint,
        )
        recovered_stale = False
        while True:
            state = self._claims.begin_or_get(command)
            if isinstance(state, ClaimedAutomaticRefresh):
                return self._run_claimed(need, state.claim)
            if isinstance(state, ExistingAutomaticRefresh):
                joined = self._wait_for_existing(
                    need,
                    state.claim,
                    allow_stale_recovery=not recovered_stale,
                )
                if joined is not None:
                    return joined
                recovered_stale = True
                continue
            assert_never(state)

    def _run_claimed(
        self,
        need: RefreshSeason,
        claim: AutomaticRefreshClaim,
    ) -> RefreshReceipt:
        try:
            outcome = self._refreshes.refresh(
                RefreshRequest(
                    competition_season_id=need.season.competition_season_id,
                    through_week=need.through_week,
                    trigger=RefreshTrigger.GENERATION,
                )
            )
        except Exception as error:
            try:
                self._claims.fail(
                    claim.id,
                    AutomaticRefreshFailure(
                        code="automatic_refresh_failed",
                        summary="Automatic season refresh failed",
                    ),
                )
            except Exception:
                pass
            raise RefreshUnavailable(
                need.season.competition_season_id,
                claim_id=claim.id,
                retryable=True,
            ) from error
        self._claims.complete(
            claim.id,
            CompleteAutomaticRefresh(
                refresh_run_id=outcome.refresh_run_id,
                refresh_status=outcome.status,
            ),
        )
        return _receipt(
            claim,
            refresh_run_id=outcome.refresh_run_id,
            status=outcome.status,
            disposition=RefreshReceiptDisposition.CLAIMED,
        )

    def _wait_for_existing(
        self,
        need: RefreshSeason,
        claim: AutomaticRefreshClaim,
        *,
        allow_stale_recovery: bool,
    ) -> RefreshReceipt | None:
        deadline = self._monotonic() + self._wait_timeout
        while True:
            stale_before = self._clock() - timedelta(seconds=self._stale_after)
            if allow_stale_recovery and self._claims.fail_stale(
                claim.active_key, stale_before
            ):
                return None
            current = self._claims.get(claim.id)
            if current.status is AutomaticRefreshClaimStatus.COMPLETED:
                if current.refresh_run_id is None or current.refresh_status is None:
                    raise RefreshUnavailable(
                        need.season.competition_season_id,
                        claim_id=current.id,
                    )
                return _receipt(
                    current,
                    refresh_run_id=current.refresh_run_id,
                    status=current.refresh_status,
                    disposition=RefreshReceiptDisposition.JOINED,
                )
            if current.status is AutomaticRefreshClaimStatus.FAILED:
                raise RefreshUnavailable(
                    need.season.competition_season_id,
                    claim_id=current.id,
                    refresh_run_id=current.refresh_run_id,
                    retryable=True,
                )
            if current.status is not AutomaticRefreshClaimStatus.RUNNING:
                assert_never(current.status)
            if self._monotonic() >= deadline:
                raise RefreshUnavailable(
                    need.season.competition_season_id,
                    claim_id=current.id,
                    retryable=True,
                )
            self._delay(self._poll_interval)


def automatic_refresh_active_key(
    need: RefreshSeason,
    *,
    policy_version: str = AUTOMATIC_REFRESH_POLICY_VERSION,
) -> str:
    """Hash the exact policy/evidence identity used for refresh coalescing."""

    return canonical_json_sha256(
        {
            "coverage_fingerprint": need.coverage_fingerprint,
            "policy_version": policy_version,
            "reason": need.reason.value,
            "season": str(need.season.competition_season_id),
            "through_week": need.through_week,
        }
    )


def _receipt(
    claim: AutomaticRefreshClaim,
    *,
    refresh_run_id: UUID,
    status: RefreshStatus,
    disposition: RefreshReceiptDisposition,
) -> RefreshReceipt:
    return RefreshReceipt(
        claim_id=claim.id,
        competition_season_id=claim.competition_season_id,
        through_week=claim.requested_through_week,
        refresh_run_id=refresh_run_id,
        status=status,
        disposition=disposition,
    )


def _positive_number(value: float, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{name} must be positive")
    return float(value)


__all__ = [
    "AUTOMATIC_REFRESH_POLICY_VERSION",
    "RefreshCoordinator",
    "RefreshReceipt",
    "RefreshReceiptDisposition",
    "automatic_refresh_active_key",
]
