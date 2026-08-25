"""Competition-scoped manager for Sleeper refresh runs."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.database.models.core import CompetitionSeason
from backend.database.models.sleeper import ApiRequest as StoredApiRequest
from backend.database.models.sleeper import RefreshRun as StoredRefreshRun
from backend.database.sessions import (
    SessionFactory,
    read_only_session,
    transaction_session,
)
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.sleeper_data.refreshes.codec import (
    decode_endpoint_scope,
    decode_refresh,
    encode_endpoint_scope,
)
from backend.resources.sleeper_data.refreshes.objects import (
    RefreshRun,
    RefreshRunPage,
    RefreshRunQuery,
    StartRefresh,
)
from backend.services.datalayer.contracts import (
    NormalizationStatus,
    RefreshStatus,
    RequestStatus,
)
from backend.services.datalayer.errors import DatalayerResourceNotFound


class RefreshRunManager:
    """Own competition-scoped refresh plans and their terminal status."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id

    def start_refresh(self, command: StartRefresh) -> RefreshRun:
        with transaction_session(self._session_factory) as session:
            self._require_season(session, command.competition_season_id)
            stored = StoredRefreshRun(
                competition_id=self._competition_id,
                competition_season_id=command.competition_season_id,
                requested_through_week=command.requested_through_week,
                endpoint_scope=encode_endpoint_scope(command.endpoint_scope),
                trigger_source=command.trigger.value,
                status=RefreshStatus.RUNNING.value,
                code_version=command.code_version,
                normalizer_version=command.normalizer_version,
                error_summary=None,
                request_count=0,
                succeeded_request_count=0,
                failed_request_count=0,
            )
            session.add(stored)
            session.flush()
            return decode_refresh(stored)

    def finish_refresh(self, refresh_id: UUID) -> RefreshRun:
        with transaction_session(self._session_factory) as session:
            refresh = self._load(session, refresh_id, lock=True)
            if refresh.status != RefreshStatus.RUNNING.value:
                return decode_refresh(refresh)
            attempts = session.scalars(
                sa.select(StoredApiRequest).where(
                    StoredApiRequest.refresh_run_id == refresh.id
                )
            ).all()
            _finish_running_refresh(refresh, attempts)
            session.flush()
            return decode_refresh(refresh)

    def finish_stale_running(
        self,
        *,
        stale_before: datetime,
        limit: int,
    ) -> tuple[RefreshRun, ...]:
        """Finish one bounded, competition-scoped batch of stale refreshes."""

        if stale_before.tzinfo is None or stale_before.utcoffset() is None:
            raise ValueError("stale_before must be timezone-aware")
        if limit < 1 or limit > 200:
            raise ValueError("stale reconciliation limit must be between 1 and 200")
        with transaction_session(self._session_factory) as session:
            refreshes = session.scalars(
                sa.select(StoredRefreshRun)
                .where(
                    StoredRefreshRun.competition_id == self._competition_id,
                    StoredRefreshRun.status == RefreshStatus.RUNNING.value,
                    StoredRefreshRun.started_at < stale_before,
                )
                .order_by(
                    StoredRefreshRun.started_at.asc(),
                    StoredRefreshRun.id.asc(),
                )
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            if not refreshes:
                return ()

            refresh_ids = [refresh.id for refresh in refreshes]
            attempts = session.scalars(
                sa.select(StoredApiRequest).where(
                    StoredApiRequest.refresh_run_id.in_(refresh_ids)
                )
            ).all()
            attempts_by_refresh: dict[UUID, list[StoredApiRequest]] = {
                refresh_id: [] for refresh_id in refresh_ids
            }
            for attempt in attempts:
                attempts_by_refresh[attempt.refresh_run_id].append(attempt)

            for refresh in refreshes:
                _finish_running_refresh(
                    refresh,
                    attempts_by_refresh[refresh.id],
                )
            session.flush()
            return tuple(decode_refresh(refresh) for refresh in refreshes)

    def get_refresh(self, refresh_id: UUID) -> RefreshRun:
        with read_only_session(self._session_factory) as session:
            return decode_refresh(self._load(session, refresh_id))

    def get_refresh_for_season(
        self,
        competition_season_id: UUID,
        refresh_id: UUID,
    ) -> RefreshRun:
        with read_only_session(self._session_factory) as session:
            self._require_season(session, competition_season_id)
            return decode_refresh(
                self._load(
                    session,
                    refresh_id,
                    competition_season_id=competition_season_id,
                )
            )

    def list_refreshes(self, query: RefreshRunQuery) -> RefreshRunPage:
        with read_only_session(self._session_factory) as session:
            self._require_season(session, query.competition_season_id)
            where = sa.and_(
                StoredRefreshRun.competition_id == self._competition_id,
                StoredRefreshRun.competition_season_id
                == query.competition_season_id,
            )
            total = cast(
                int,
                session.scalar(
                    sa.select(sa.func.count())
                    .select_from(StoredRefreshRun)
                    .where(where)
                ),
            )
            rows = session.scalars(
                sa.select(StoredRefreshRun)
                .where(where)
                .order_by(
                    StoredRefreshRun.started_at.desc(),
                    StoredRefreshRun.id.desc(),
                )
                .limit(query.limit)
                .offset(query.offset)
            ).all()
            return RefreshRunPage(
                items=tuple(decode_refresh(row) for row in rows),
                total=total,
                limit=query.limit,
                offset=query.offset,
            )

    def _load(
        self,
        session: Session,
        refresh_id: UUID,
        *,
        lock: bool = False,
        competition_season_id: UUID | None = None,
    ) -> StoredRefreshRun:
        conditions = [
            StoredRefreshRun.id == refresh_id,
            StoredRefreshRun.competition_id == self._competition_id,
        ]
        if competition_season_id is not None:
            conditions.append(
                StoredRefreshRun.competition_season_id == competition_season_id
            )
        statement = sa.select(StoredRefreshRun).where(*conditions)
        if lock:
            statement = statement.with_for_update()
        stored = session.scalar(statement)
        if stored is None:
            raise DatalayerResourceNotFound("refresh", str(refresh_id))
        return stored

    def _require_season(
        self,
        session: Session,
        season_id: UUID,
    ) -> CompetitionSeason:
        season = session.scalar(
            sa.select(CompetitionSeason).where(
                CompetitionSeason.id == season_id,
                CompetitionSeason.competition_id == self._competition_id,
            )
        )
        if season is None:
            raise DatalayerResourceNotFound("competition_season", str(season_id))
        return season


def _request_order(request: StoredApiRequest) -> tuple[datetime, int]:
    return request.requested_at, request.id.int


def _request_is_normalized(request: StoredApiRequest) -> bool:
    return (
        request.status == RequestStatus.SUCCEEDED.value
        and request.is_complete
        and request.normalization_status == NormalizationStatus.SUCCEEDED.value
    )


def _finish_running_refresh(
    refresh: StoredRefreshRun,
    attempts: Sequence[StoredApiRequest],
) -> None:
    plan = decode_endpoint_scope(refresh.endpoint_scope)
    latest: dict[str, StoredApiRequest] = {}
    for attempt in attempts:
        current = latest.get(attempt.scope_key)
        if current is None or _request_order(attempt) > _request_order(current):
            latest[attempt.scope_key] = attempt

    succeeded = 0
    required_successes = 0
    required_failures = 0
    failed_scopes: list[str] = []
    for planned in plan:
        attempt = latest.get(planned.scope_key.value)
        successful = attempt is not None and _request_is_normalized(attempt)
        if successful:
            succeeded += 1
            if planned.required:
                required_successes += 1
        else:
            failed_scopes.append(planned.scope_key.value)
            if planned.required:
                required_failures += 1

    if required_failures == 0:
        status = RefreshStatus.SUCCEEDED
    elif required_successes:
        status = RefreshStatus.PARTIAL
    else:
        status = RefreshStatus.FAILED
    refresh.status = status.value
    refresh.completed_at = sa.func.now()
    refresh.request_count = len(plan)
    refresh.succeeded_request_count = succeeded
    refresh.failed_request_count = len(plan) - succeeded
    refresh.error_summary = (
        None
        if not failed_scopes
        else {"code": "refresh_scopes_failed", "scope_keys": failed_scopes}
    )
