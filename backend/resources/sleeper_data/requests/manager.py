"""Competition-scoped manager for Sleeper request observations and payloads."""

from __future__ import annotations

from collections.abc import Collection
from typing import Any, cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.database.models.core import CompetitionSeason
from backend.database.models.sleeper import ApiPayload as StoredApiPayload
from backend.database.models.sleeper import ApiRequest as StoredApiRequest
from backend.database.models.sleeper import RefreshRun as StoredRefreshRun
from backend.database.sessions import (
    SessionFactory,
    read_only_session,
    transaction_session,
)
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.sleeper_data.refreshes.codec import decode_endpoint_scope
from backend.resources.sleeper_data.requests.codec import (
    decode_api_request,
    jsonb_expression,
    parse_jsonb_text,
)
from backend.resources.sleeper_data.requests.objects import (
    ApiRequest,
    ApiRequestCandidate,
    InlineVerifiedPayload,
    LatestCompleteCandidatesQuery,
    NormalizationRejection,
    ObjectVerifiedPayload,
    Page,
    RecordApiAttempt,
    SnapshotCandidateQuery,
    VerifiedPayload,
)
from backend.services.datalayer.canonical_json import canonical_json_sha256
from backend.services.datalayer.contracts import (
    NormalizationStatus,
    RefreshStatus,
    RequestStatus,
)
from backend.services.datalayer.errors import (
    DatalayerResourceNotFound,
    DatalayerScopeConflict,
    InvalidDatalayerRequest,
)
from backend.services.datalayer.sleeper.responses import (
    SuccessfulSourceAttempt,
)
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey

_GLOBAL_ENDPOINTS = {EndpointKind.NFL_STATE, EndpointKind.PLAYER_CATALOG}


class ApiRequestManager:
    """Own request audit observations and content-addressed payload receipts."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id

    def record_attempt(self, command: RecordApiAttempt) -> ApiRequest:
        with transaction_session(self._session_factory) as session:
            refresh = self._load_refresh(session, command.refresh_run_id, lock=True)
            if refresh.status != RefreshStatus.RUNNING.value:
                raise DatalayerScopeConflict(
                    "attempts can only be added to a running refresh"
                )
            self._validate_attempt_scope(refresh, command)
            attempt = command.attempt
            payload_id: UUID | None = None
            response_sha256: str | None = None
            error: dict[str, Any] | None = None
            if isinstance(attempt, SuccessfulSourceAttempt):
                payload_id = self._record_payload(session, command)
                response_sha256 = attempt.raw_sha256
                request_status = RequestStatus.SUCCEEDED
                normalization_status = (
                    NormalizationStatus.PENDING
                    if command.completeness.is_complete
                    else NormalizationStatus.REJECTED
                )
            else:
                request_status = attempt.status
                normalization_status = NormalizationStatus.NOT_APPLICABLE
                error = attempt.error.model_dump(mode="json")

            stored = StoredApiRequest(
                id=uuid4(),
                refresh_run_id=refresh.id,
                competition_season_id=(
                    None
                    if attempt.endpoint.endpoint_kind in _GLOBAL_ENDPOINTS
                    else refresh.competition_season_id
                ),
                endpoint_kind=attempt.endpoint.endpoint_kind.value,
                scope_key=attempt.endpoint.scope_key.value,
                request_path=attempt.endpoint.path,
                request_parameters=attempt.endpoint.parameters,
                week=attempt.endpoint.week,
                bracket_kind=attempt.endpoint.bracket_kind,
                requested_at=attempt.requested_at,
                completed_at=attempt.completed_at,
                latency_ms=attempt.latency_ms,
                status=request_status.value,
                http_status=attempt.http_status,
                error=error,
                is_complete=command.completeness.is_complete,
                completeness_reason=command.completeness.reason,
                payload_id=payload_id,
                response_sha256=response_sha256,
                normalization_status=normalization_status.value,
            )
            session.add(stored)
            session.flush()
            return decode_api_request(stored)

    def reject_normalization(
        self,
        request_id: UUID,
        rejection: NormalizationRejection,
    ) -> ApiRequest:
        with transaction_session(self._session_factory) as session:
            request, refresh = self._load_request_with_refresh(
                session, request_id, lock=True
            )
            if request.normalization_status != NormalizationStatus.PENDING.value:
                raise DatalayerScopeConflict(
                    "only a pending complete request can be rejected"
                )
            request.normalization_status = NormalizationStatus.REJECTED.value
            request.normalizer_version = refresh.normalizer_version
            request.normalized_at = sa.func.now()
            request.error = {
                "stage": "normalization",
                "code": rejection.code,
                "summary": rejection.summary,
            }
            session.flush()
            return decode_api_request(request)

    def list_refresh_requests(
        self,
        refresh_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Page[ApiRequest]:
        if not 1 <= limit <= 200 or offset < 0:
            raise InvalidDatalayerRequest("invalid request page")
        with read_only_session(self._session_factory) as session:
            refresh = self._load_refresh(session, refresh_id)
            where = StoredApiRequest.refresh_run_id == refresh.id
            total = session.scalar(
                sa.select(sa.func.count()).select_from(StoredApiRequest).where(where)
            )
            rows = session.scalars(
                sa.select(StoredApiRequest)
                .where(where)
                .order_by(StoredApiRequest.requested_at, StoredApiRequest.id)
                .limit(limit)
                .offset(offset)
            ).all()
            return Page[ApiRequest](
                items=tuple(decode_api_request(row) for row in rows),
                total=cast(int, total),
                limit=limit,
                offset=offset,
            )

    def list_snapshot_candidates(
        self,
        query: SnapshotCandidateQuery,
    ) -> tuple[ApiRequestCandidate, ...]:
        with read_only_session(self._session_factory) as session:
            self._require_season(session, query.competition_season_id)
            scope_values = [scope.value for scope in query.scope_keys]
            allowed_global = [kind.value for kind in _GLOBAL_ENDPOINTS]
            rows = session.scalars(
                sa.select(StoredApiRequest)
                .join(
                    StoredRefreshRun,
                    StoredRefreshRun.id == StoredApiRequest.refresh_run_id,
                )
                .where(
                    StoredApiRequest.scope_key.in_(scope_values),
                    StoredApiRequest.status == RequestStatus.SUCCEEDED.value,
                    StoredApiRequest.is_complete.is_(True),
                    StoredApiRequest.payload_id.is_not(None),
                    StoredApiRequest.response_sha256.is_not(None),
                    sa.or_(
                        StoredApiRequest.competition_season_id
                        == query.competition_season_id,
                        sa.and_(
                            StoredApiRequest.competition_season_id.is_(None),
                            StoredApiRequest.endpoint_kind.in_(allowed_global),
                        ),
                    ),
                    sa.or_(
                        StoredApiRequest.week.is_(None),
                        StoredApiRequest.week <= query.through_week,
                    ),
                )
                .order_by(
                    StoredApiRequest.scope_key,
                    StoredApiRequest.requested_at.desc(),
                    StoredApiRequest.id.desc(),
                )
            ).all()
            return tuple(
                ApiRequestCandidate(
                    request_id=row.id,
                    competition_season_id=row.competition_season_id,
                    endpoint_kind=EndpointKind(row.endpoint_kind),
                    scope_key=ScopeKey.parse(row.scope_key),
                    week=row.week,
                    bracket_kind=cast(Any, row.bracket_kind),
                    requested_at=row.requested_at,
                    completed_at=row.completed_at,
                    payload_id=cast(UUID, row.payload_id),
                    response_sha256=cast(str, row.response_sha256),
                )
                for row in rows
            )

    def list_latest_complete_candidates(
        self,
        query: LatestCompleteCandidatesQuery,
    ) -> tuple[ApiRequestCandidate, ...]:
        """Return at most one deterministic eligible observation per scope."""

        with read_only_session(self._session_factory) as session:
            scope_values = [scope.value for scope in query.scope_keys]
            rank = sa.func.row_number().over(
                partition_by=StoredApiRequest.scope_key,
                order_by=(
                    StoredApiRequest.requested_at.desc(),
                    StoredApiRequest.id.desc(),
                ),
            ).label("candidate_rank")
            ranked = (
                sa.select(StoredApiRequest.id.label("request_id"), rank)
                .join(
                    StoredRefreshRun,
                    StoredRefreshRun.id == StoredApiRequest.refresh_run_id,
                )
                .where(
                    StoredRefreshRun.competition_id == self._competition_id,
                    StoredApiRequest.scope_key.in_(scope_values),
                    StoredApiRequest.status == RequestStatus.SUCCEEDED.value,
                    StoredApiRequest.is_complete.is_(True),
                    StoredApiRequest.payload_id.is_not(None),
                    StoredApiRequest.response_sha256.is_not(None),
                )
                .subquery()
            )
            rows = session.scalars(
                sa.select(StoredApiRequest)
                .join(ranked, ranked.c.request_id == StoredApiRequest.id)
                .where(ranked.c.candidate_rank == 1)
                .order_by(StoredApiRequest.scope_key)
            ).all()
            return tuple(_candidate(row) for row in rows)

    def get_latest_complete_season_request(
        self,
        competition_season_id: UUID,
        endpoint_kind: EndpointKind,
    ) -> ApiRequestCandidate | None:
        if endpoint_kind in _GLOBAL_ENDPOINTS:
            raise InvalidDatalayerRequest(
                "latest season request requires a season-scoped endpoint"
            )
        with read_only_session(self._session_factory) as session:
            self._require_season(session, competition_season_id)
            row = session.scalar(
                sa.select(StoredApiRequest)
                .join(
                    StoredRefreshRun,
                    StoredRefreshRun.id == StoredApiRequest.refresh_run_id,
                )
                .where(
                    StoredRefreshRun.competition_id == self._competition_id,
                    StoredApiRequest.competition_season_id
                    == competition_season_id,
                    StoredApiRequest.endpoint_kind == endpoint_kind.value,
                    StoredApiRequest.status == RequestStatus.SUCCEEDED.value,
                    StoredApiRequest.is_complete.is_(True),
                    StoredApiRequest.payload_id.is_not(None),
                    StoredApiRequest.response_sha256.is_not(None),
                )
                .order_by(
                    StoredApiRequest.requested_at.desc(),
                    StoredApiRequest.id.desc(),
                )
                .limit(1)
            )
            if row is None:
                return None
            return ApiRequestCandidate(
                request_id=row.id,
                competition_season_id=row.competition_season_id,
                endpoint_kind=EndpointKind(row.endpoint_kind),
                scope_key=ScopeKey.parse(row.scope_key),
                week=row.week,
                bracket_kind=cast(Any, row.bracket_kind),
                requested_at=row.requested_at,
                completed_at=row.completed_at,
                payload_id=cast(UUID, row.payload_id),
                response_sha256=cast(str, row.response_sha256),
            )

    def resolve_verified_payloads(
        self,
        request_ids: Collection[UUID],
    ) -> tuple[VerifiedPayload, ...]:
        ordered = tuple(request_ids)
        if len(set(ordered)) != len(ordered):
            raise InvalidDatalayerRequest("payload request IDs must be unique")
        if not ordered:
            return ()
        with read_only_session(self._session_factory) as session:
            rows = session.execute(
                sa.select(
                    StoredApiRequest,
                    StoredApiPayload,
                    sa.cast(StoredApiPayload.inline_payload, sa.Text).label(
                        "inline_text"
                    ),
                    StoredRefreshRun.competition_id,
                )
                .join(
                    StoredApiPayload,
                    StoredApiPayload.id == StoredApiRequest.payload_id,
                )
                .join(
                    StoredRefreshRun,
                    StoredRefreshRun.id == StoredApiRequest.refresh_run_id,
                )
                .where(StoredApiRequest.id.in_(ordered))
            ).all()
            by_id = {row[0].id: row for row in rows}
            result: list[VerifiedPayload] = []
            for request_id in ordered:
                row = by_id.get(request_id)
                if row is None:
                    raise DatalayerResourceNotFound(
                        "api_request_payload", str(request_id)
                    )
                request, payload, inline_text, request_competition_id = row
                if (
                    request_competition_id != self._competition_id
                    and request.endpoint_kind
                    not in {kind.value for kind in _GLOBAL_ENDPOINTS}
                ):
                    raise DatalayerResourceNotFound(
                        "api_request_payload", str(request_id)
                    )
                _require_eligible_request(request)
                if request.response_sha256 != payload.sha256_hash:
                    raise DatalayerScopeConflict(
                        "request payload receipt is inconsistent"
                    )
                common = {
                    "request_id": request.id,
                    "scope_key": ScopeKey.parse(request.scope_key),
                    "sha256": payload.sha256_hash,
                    "byte_length": payload.byte_length,
                    "media_type": payload.media_type,
                }
                if payload.storage_kind == "inline_json":
                    if inline_text is None:
                        raise DatalayerScopeConflict(
                            "inline payload content is missing"
                        )
                    parsed = parse_jsonb_text(inline_text)
                    if canonical_json_sha256(parsed) != payload.sha256_hash:
                        raise DatalayerScopeConflict(
                            "inline payload bytes do not match their receipt"
                        )
                    result.append(InlineVerifiedPayload(payload=parsed, **common))
                elif payload.storage_kind == "object":
                    if payload.object_storage_key is None:
                        raise DatalayerScopeConflict("object payload key is missing")
                    result.append(
                        ObjectVerifiedPayload(
                            storage_key=payload.object_storage_key,
                            **common,
                        )
                    )
                else:
                    raise DatalayerScopeConflict("payload storage kind is unsupported")
            return tuple(result)

    def _load_refresh(
        self,
        session: Session,
        refresh_id: UUID,
        *,
        lock: bool = False,
    ) -> StoredRefreshRun:
        statement = sa.select(StoredRefreshRun).where(
            StoredRefreshRun.id == refresh_id,
            StoredRefreshRun.competition_id == self._competition_id,
        )
        if lock:
            statement = statement.with_for_update()
        stored = session.scalar(statement)
        if stored is None:
            raise DatalayerResourceNotFound("refresh", str(refresh_id))
        return stored

    def _load_request_with_refresh(
        self,
        session: Session,
        request_id: UUID,
        *,
        lock: bool = False,
    ) -> tuple[StoredApiRequest, StoredRefreshRun]:
        statement = (
            sa.select(StoredApiRequest, StoredRefreshRun)
            .join(
                StoredRefreshRun,
                StoredRefreshRun.id == StoredApiRequest.refresh_run_id,
            )
            .where(
                StoredApiRequest.id == request_id,
                StoredRefreshRun.competition_id == self._competition_id,
            )
        )
        if lock:
            statement = statement.with_for_update(of=StoredApiRequest)
        row = session.execute(statement).one_or_none()
        if row is None:
            raise DatalayerResourceNotFound("api_request", str(request_id))
        return row[0], row[1]

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

    @staticmethod
    def _validate_attempt_scope(
        refresh: StoredRefreshRun,
        command: RecordApiAttempt,
    ) -> None:
        endpoint = command.attempt.endpoint
        planned = {
            item.scope_key: item
            for item in decode_endpoint_scope(refresh.endpoint_scope)
        }.get(endpoint.scope_key)
        if planned is None or planned.endpoint_kind is not endpoint.endpoint_kind:
            raise DatalayerScopeConflict(
                "source attempt is not part of the refresh plan"
            )
        parts = endpoint.scope_key.value.split(":")
        if endpoint.endpoint_kind in _GLOBAL_ENDPOINTS:
            if parts != [endpoint.endpoint_kind.value, "nfl"]:
                raise DatalayerScopeConflict("global endpoint has an invalid scope")
        elif len(parts) < 2 or parts[1] != str(refresh.competition_season_id):
            raise DatalayerScopeConflict(
                "source attempt is outside the refresh season"
            )

    @staticmethod
    def _record_payload(session: Session, command: RecordApiAttempt) -> UUID:
        attempt = cast(SuccessfulSourceAttempt, command.attempt)
        receipt = command.object_receipt
        payload_id = uuid4()
        values: dict[str, Any] = {
            "id": payload_id,
            "sha256_hash": attempt.raw_sha256,
            "byte_length": attempt.byte_length,
            "media_type": attempt.media_type,
            "storage_kind": "object" if receipt is not None else "inline_json",
            "inline_payload": (
                sa.null() if receipt is not None else jsonb_expression(attempt.payload)
            ),
            "object_storage_key": None if receipt is None else receipt.storage_key,
        }
        statement = (
            pg_insert(StoredApiPayload.__table__)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[StoredApiPayload.sha256_hash])
        )
        session.execute(statement)
        stored = session.scalar(
            sa.select(StoredApiPayload).where(
                StoredApiPayload.sha256_hash == attempt.raw_sha256
            )
        )
        if stored is None:
            raise RuntimeError("payload upsert did not produce a stored receipt")
        if (
            stored.byte_length != attempt.byte_length
            or stored.media_type != attempt.media_type
        ):
            raise DatalayerScopeConflict(
                "stored payload receipt conflicts with its hash"
            )
        if stored.storage_kind == "object" and stored.object_storage_key is None:
            raise RuntimeError("stored object payload has no storage key")
        return stored.id


def _require_eligible_request(request: StoredApiRequest) -> None:
    if (
        request.status != RequestStatus.SUCCEEDED.value
        or not request.is_complete
        or request.payload_id is None
        or request.response_sha256 is None
    ):
        raise DatalayerScopeConflict("request is not eligible for normalization")


def _candidate(row: StoredApiRequest) -> ApiRequestCandidate:
    return ApiRequestCandidate(
        request_id=row.id,
        competition_season_id=row.competition_season_id,
        endpoint_kind=EndpointKind(row.endpoint_kind),
        scope_key=ScopeKey.parse(row.scope_key),
        week=row.week,
        bracket_kind=cast(Any, row.bracket_kind),
        requested_at=row.requested_at,
        completed_at=row.completed_at,
        payload_id=cast(UUID, row.payload_id),
        response_sha256=cast(str, row.response_sha256),
    )
