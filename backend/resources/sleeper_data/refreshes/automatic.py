"""Durable competition-scoped coordination for automatic refresh work."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.database.models.core import CompetitionSeason
from backend.database.models.sleeper import (
    AutomaticRefreshClaim as StoredAutomaticRefreshClaim,
)
from backend.database.sessions import SessionFactory, read_only_session, transaction_session
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.sleeper_data.refreshes.objects import (
    AutomaticRefreshClaim,
    AutomaticRefreshClaimState,
    AutomaticRefreshClaimStatus,
    AutomaticRefreshFailure,
    ClaimAutomaticRefresh,
    ClaimedAutomaticRefresh,
    CompleteAutomaticRefresh,
    ExistingAutomaticRefresh,
    RefreshNeedReason,
)
from backend.services.datalayer.errors import (
    DatalayerResourceNotFound,
    DatalayerScopeConflict,
)
from backend.services.datalayer.contracts import RefreshStatus


class AutomaticRefreshClaimManager:
    """Own one active automatic refresh claim per canonical evidence key."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id

    def begin_or_get(
        self,
        command: ClaimAutomaticRefresh,
    ) -> AutomaticRefreshClaimState:
        with transaction_session(self._session_factory) as session:
            self._require_season(session, command.competition_season_id)
            claim_id = uuid4()
            statement = (
                pg_insert(StoredAutomaticRefreshClaim)
                .values(
                    id=claim_id,
                    competition_id=self._competition_id,
                    competition_season_id=command.competition_season_id,
                    active_key=command.active_key,
                    requested_through_week=command.requested_through_week,
                    policy_version=command.policy_version,
                    reason=command.reason.value,
                    coverage_fingerprint=command.coverage_fingerprint,
                    status=AutomaticRefreshClaimStatus.RUNNING.value,
                    refresh_run_id=None,
                    refresh_status=None,
                    failure_summary=None,
                    completed_at=None,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        StoredAutomaticRefreshClaim.competition_id,
                        StoredAutomaticRefreshClaim.active_key,
                    ],
                    index_where=(
                        StoredAutomaticRefreshClaim.status
                        == AutomaticRefreshClaimStatus.RUNNING.value
                    ),
                )
            )
            inserted = session.scalar(
                statement.returning(StoredAutomaticRefreshClaim.id)
            )
            stored = session.scalar(
                sa.select(StoredAutomaticRefreshClaim).where(
                    StoredAutomaticRefreshClaim.competition_id
                    == self._competition_id,
                    StoredAutomaticRefreshClaim.active_key == command.active_key,
                    StoredAutomaticRefreshClaim.status
                    == AutomaticRefreshClaimStatus.RUNNING.value,
                )
            )
            if stored is None:
                raise RuntimeError("automatic refresh claim did not produce a row")
            self._validate_identity(stored, command)
            claim = _decode_claim(stored)
            if inserted == claim_id and stored.id == claim_id:
                return ClaimedAutomaticRefresh(claim=claim)
            return ExistingAutomaticRefresh(claim=claim)

    def complete(
        self,
        claim_id: UUID,
        command: CompleteAutomaticRefresh,
    ) -> AutomaticRefreshClaim:
        with transaction_session(self._session_factory) as session:
            stored = self._load(session, claim_id, lock=True)
            if stored.status == AutomaticRefreshClaimStatus.COMPLETED.value:
                claim = _decode_claim(stored)
                if (
                    claim.refresh_run_id != command.refresh_run_id
                    or claim.refresh_status is not command.refresh_status
                ):
                    raise DatalayerScopeConflict(
                        "automatic refresh claim has another terminal receipt"
                    )
                return claim
            if stored.status != AutomaticRefreshClaimStatus.RUNNING.value:
                raise DatalayerScopeConflict(
                    "only a running automatic refresh claim can complete"
                )
            stored.status = AutomaticRefreshClaimStatus.COMPLETED.value
            stored.refresh_run_id = command.refresh_run_id
            stored.refresh_status = command.refresh_status.value
            stored.failure_summary = None
            stored.completed_at = sa.func.now()
            session.flush()
            return _decode_claim(stored)

    def fail(
        self,
        claim_id: UUID,
        failure: AutomaticRefreshFailure,
    ) -> AutomaticRefreshClaim:
        with transaction_session(self._session_factory) as session:
            stored = self._load(session, claim_id, lock=True)
            if stored.status == AutomaticRefreshClaimStatus.FAILED.value:
                return _decode_claim(stored)
            if stored.status != AutomaticRefreshClaimStatus.RUNNING.value:
                raise DatalayerScopeConflict(
                    "only a running automatic refresh claim can fail"
                )
            stored.status = AutomaticRefreshClaimStatus.FAILED.value
            stored.refresh_status = None
            stored.failure_summary = failure.model_dump(mode="json")
            stored.completed_at = sa.func.now()
            session.flush()
            return _decode_claim(stored)

    def fail_stale(self, active_key: str, stale_before: datetime) -> bool:
        if stale_before.tzinfo is None or stale_before.utcoffset() is None:
            raise ValueError("stale_before must be timezone-aware")
        failure = AutomaticRefreshFailure(
            code="automatic_refresh_stale",
            summary="Automatic refresh exceeded the stale threshold",
        )
        with transaction_session(self._session_factory) as session:
            result = session.execute(
                sa.update(StoredAutomaticRefreshClaim)
                .where(
                    StoredAutomaticRefreshClaim.competition_id
                    == self._competition_id,
                    StoredAutomaticRefreshClaim.active_key == active_key,
                    StoredAutomaticRefreshClaim.status
                    == AutomaticRefreshClaimStatus.RUNNING.value,
                    StoredAutomaticRefreshClaim.started_at < stale_before,
                )
                .values(
                    status=AutomaticRefreshClaimStatus.FAILED.value,
                    failure_summary=failure.model_dump(mode="json"),
                    completed_at=sa.func.now(),
                )
                .execution_options(synchronize_session=False)
            )
            return cast(int, result.rowcount) == 1

    def get(self, claim_id: UUID) -> AutomaticRefreshClaim:
        with read_only_session(self._session_factory) as session:
            return _decode_claim(self._load(session, claim_id))

    def _load(
        self,
        session: Session,
        claim_id: UUID,
        *,
        lock: bool = False,
    ) -> StoredAutomaticRefreshClaim:
        statement = sa.select(StoredAutomaticRefreshClaim).where(
            StoredAutomaticRefreshClaim.id == claim_id,
            StoredAutomaticRefreshClaim.competition_id == self._competition_id,
        )
        if lock:
            statement = statement.with_for_update()
        stored = session.scalar(statement)
        if stored is None:
            raise DatalayerResourceNotFound("automatic_refresh_claim", str(claim_id))
        return stored

    def _require_season(self, session: Session, season_id: UUID) -> None:
        exists = session.scalar(
            sa.select(CompetitionSeason.id).where(
                CompetitionSeason.id == season_id,
                CompetitionSeason.competition_id == self._competition_id,
            )
        )
        if exists is None:
            raise DatalayerResourceNotFound("competition_season", str(season_id))

    @staticmethod
    def _validate_identity(
        stored: StoredAutomaticRefreshClaim,
        command: ClaimAutomaticRefresh,
    ) -> None:
        if (
            stored.competition_season_id != command.competition_season_id
            or stored.requested_through_week != command.requested_through_week
            or stored.policy_version != command.policy_version
            or RefreshNeedReason(stored.reason) is not command.reason
            or stored.coverage_fingerprint != command.coverage_fingerprint
        ):
            raise DatalayerScopeConflict(
                "automatic refresh active key conflicts with its canonical identity"
            )


def _decode_claim(stored: StoredAutomaticRefreshClaim) -> AutomaticRefreshClaim:
    failure_value = cast(dict[str, Any] | None, stored.failure_summary)
    return AutomaticRefreshClaim(
        id=stored.id,
        competition_id=stored.competition_id,
        competition_season_id=stored.competition_season_id,
        active_key=stored.active_key,
        requested_through_week=stored.requested_through_week,
        policy_version=stored.policy_version,
        reason=RefreshNeedReason(stored.reason),
        coverage_fingerprint=stored.coverage_fingerprint,
        status=AutomaticRefreshClaimStatus(stored.status),
        refresh_run_id=stored.refresh_run_id,
        refresh_status=(
            None if stored.refresh_status is None else RefreshStatus(stored.refresh_status)
        ),
        failure=(
            None
            if failure_value is None
            else AutomaticRefreshFailure.model_validate(failure_value)
        ),
        started_at=stored.started_at,
        completed_at=stored.completed_at,
    )


__all__ = ["AutomaticRefreshClaimManager"]
