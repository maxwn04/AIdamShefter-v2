"""Competition-scoped manager for atomic normalized scope transitions."""

from datetime import datetime
from typing import assert_never, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.database.models.sleeper import (
    ApiRequest,
    NormalizedScope,
    RefreshRun,
)
from backend.database.sessions import SessionFactory, transaction_session
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.sleeper_data.normalized_scopes.objects import ApplyResult
from backend.resources.sleeper_data.projections import write_endpoint_records
from backend.services.datalayer.contracts import (
    ApplyDisposition,
    NormalizationStatus,
    RequestStatus,
)
from backend.services.datalayer.errors import (
    DatalayerResourceNotFound,
    DatalayerScopeConflict,
)
from backend.services.datalayer.sleeper.endpoints.contracts import (
    EndpointRecords,
    LeagueEndpointRecords,
    LeagueRostersEndpointRecords,
    LeagueUsersEndpointRecords,
    LosersBracketEndpointRecords,
    MatchupsEndpointRecords,
    NflStateEndpointRecords,
    PlayerCatalogEndpointRecords,
    TradedPicksEndpointRecords,
    TransactionsEndpointRecords,
    WinnersBracketEndpointRecords,
)
from backend.services.datalayer.sleeper.scope import ScopeKey


class NormalizedScopeManager:
    """Own atomic projection and provenance-head updates for endpoint scopes."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id

    def apply_scope(
        self,
        request_id: UUID,
        records: EndpointRecords,
    ) -> ApplyResult:
        """Apply one complete observation and advance its head atomically."""

        with transaction_session(self._session_factory) as session:
            request, refresh = self._load_request_with_refresh(
                session, request_id, lock=True
            )
            _require_eligible_request(request)
            if request.endpoint_kind != records.endpoint_kind.value:
                raise DatalayerScopeConflict(
                    "endpoint records do not match the recorded request"
                )

            _ = session.execute(
                sa.select(
                    sa.func.pg_advisory_xact_lock(
                        sa.func.hashtextextended(request.scope_key, 0)
                    )
                )
            ).scalar_one()
            head = session.get(
                NormalizedScope,
                request.scope_key,
                with_for_update=True,
            )
            row_count = endpoint_record_count(records)
            if head is not None:
                if head.source_api_request_id == request.id:
                    return ApplyResult(
                        request_id=request.id,
                        scope_key=ScopeKey.parse(request.scope_key),
                        disposition=ApplyDisposition.ALREADY_APPLIED,
                        head_request_id=request.id,
                        normalized_row_count=head.normalized_row_count,
                        changed_current_view=False,
                    )
                previous = session.get(ApiRequest, head.source_api_request_id)
                if previous is None:
                    raise RuntimeError(
                        "normalized scope head references a missing request"
                    )
                if request_order(request) < request_order(previous):
                    _mark_normalized(request, refresh.normalizer_version)
                    return ApplyResult(
                        request_id=request.id,
                        scope_key=ScopeKey.parse(request.scope_key),
                        disposition=ApplyDisposition.STALE_IGNORED,
                        head_request_id=head.source_api_request_id,
                        normalized_row_count=head.normalized_row_count,
                        changed_current_view=False,
                    )
                if request.response_sha256 == head.response_sha256:
                    head.source_api_request_id = request.id
                    head.normalized_row_count = row_count
                    head.applied_at = sa.func.now()
                    _mark_normalized(request, refresh.normalizer_version)
                    return ApplyResult(
                        request_id=request.id,
                        scope_key=ScopeKey.parse(request.scope_key),
                        disposition=ApplyDisposition.IDENTICAL_HEAD_ADVANCED,
                        head_request_id=request.id,
                        normalized_row_count=row_count,
                        changed_current_view=False,
                    )

            write_endpoint_records(
                session,
                self._competition_id,
                request,
                records,
            )
            if head is None:
                head = NormalizedScope(
                    scope_key=request.scope_key,
                    source_api_request_id=request.id,
                    response_sha256=cast(str, request.response_sha256),
                    normalized_row_count=row_count,
                )
                session.add(head)
            else:
                head.source_api_request_id = request.id
                head.response_sha256 = cast(str, request.response_sha256)
                head.normalized_row_count = row_count
                head.applied_at = sa.func.now()
            _mark_normalized(request, refresh.normalizer_version)
            return ApplyResult(
                request_id=request.id,
                scope_key=ScopeKey.parse(request.scope_key),
                disposition=ApplyDisposition.APPLIED,
                head_request_id=request.id,
                normalized_row_count=row_count,
                changed_current_view=True,
            )

    def _load_request_with_refresh(
        self,
        session: Session,
        request_id: UUID,
        *,
        lock: bool = False,
    ) -> tuple[ApiRequest, RefreshRun]:
        statement = (
            sa.select(ApiRequest, RefreshRun)
            .join(RefreshRun, RefreshRun.id == ApiRequest.refresh_run_id)
            .where(
                ApiRequest.id == request_id,
                RefreshRun.competition_id == self._competition_id,
            )
        )
        if lock:
            statement = statement.with_for_update(of=ApiRequest)
        row = session.execute(statement).one_or_none()
        if row is None:
            raise DatalayerResourceNotFound("api_request", str(request_id))
        return row[0], row[1]


def endpoint_record_count(records: EndpointRecords) -> int:
    """Count endpoint records, excluding auxiliary derived seed operations."""

    if isinstance(records, LeagueEndpointRecords):
        return 1
    if isinstance(records, LeagueUsersEndpointRecords):
        return len(records.users) + len(records.league_users)
    if isinstance(records, NflStateEndpointRecords):
        return 1
    if isinstance(records, PlayerCatalogEndpointRecords):
        return len(records.players)
    if isinstance(records, LeagueRostersEndpointRecords):
        return len(records.rosters) + len(records.managers) + len(records.players)
    if isinstance(records, TradedPicksEndpointRecords):
        return len(records.picks)
    if isinstance(records, MatchupsEndpointRecords):
        return len(records.matchups) + len(records.player_performances)
    if isinstance(records, TransactionsEndpointRecords):
        return len(records.transactions) + len(records.moves)
    if isinstance(
        records, (WinnersBracketEndpointRecords, LosersBracketEndpointRecords)
    ):
        return len(records.matchups)
    assert_never(records)


def request_order(request: ApiRequest) -> tuple[datetime, int]:
    return request.requested_at, request.id.int


def _require_eligible_request(request: ApiRequest) -> None:
    if (
        request.status != RequestStatus.SUCCEEDED.value
        or not request.is_complete
        or request.payload_id is None
        or request.response_sha256 is None
    ):
        raise DatalayerScopeConflict("request is not eligible for normalization")


def _mark_normalized(request: ApiRequest, version: str) -> None:
    request.normalization_status = NormalizationStatus.SUCCEEDED.value
    request.normalizer_version = version
    request.normalized_at = sa.func.now()
