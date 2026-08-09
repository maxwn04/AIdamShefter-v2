"""HTTP schemas for Sleeper data refresh workflows."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.services.datalayer.contracts import (
    NormalizationStatus,
    RefreshOutcome,
    RefreshStatus,
    RequestStatus,
)
from backend.resources.sleeper_data.objects import (
    ApiRequest,
    Page,
    RefreshRun,
)


class DataRefreshCreateRequest(BaseModel):
    """Caller-controlled portion of a standard manual refresh."""

    model_config = ConfigDict(extra="forbid")

    through_week: int | None = Field(default=None, ge=1, le=18)


class DataRefreshScopeResponse(BaseModel):
    """Sanitized result for one planned endpoint scope."""

    scope_key: str
    api_request_id: UUID
    fetch_status: RequestStatus
    normalization_status: NormalizationStatus
    changed_current_view: bool
    warning_codes: tuple[str, ...]


class DataRefreshResponse(BaseModel):
    """Terminal public representation of a synchronous refresh."""

    refresh_run_id: UUID
    status: RefreshStatus
    requested_scope_count: int
    succeeded_scope_count: int
    failed_scope_count: int
    scope_results: tuple[DataRefreshScopeResponse, ...]

    @classmethod
    def from_outcome(cls, outcome: RefreshOutcome) -> "DataRefreshResponse":
        return cls(
            refresh_run_id=outcome.refresh_run_id,
            status=outcome.status,
            requested_scope_count=outcome.requested_scope_count,
            succeeded_scope_count=outcome.succeeded_scope_count,
            failed_scope_count=outcome.failed_scope_count,
            scope_results=tuple(
                DataRefreshScopeResponse(
                    scope_key=result.scope_key.value,
                    api_request_id=result.api_request_id,
                    fetch_status=result.fetch_status,
                    normalization_status=result.normalization_status,
                    changed_current_view=result.changed_current_view,
                    warning_codes=result.warning_codes,
                )
                for result in outcome.scope_results
            ),
        )


class DataRefreshPlanItemResponse(BaseModel):
    scope_key: str
    endpoint_kind: str
    required: bool
    dependency_scope_keys: tuple[str, ...]


class DataRefreshAuditResponse(BaseModel):
    """Stored refresh audit without payload locations or internal errors."""

    refresh_run_id: UUID
    competition_id: UUID
    competition_season_id: UUID
    requested_through_week: int | None
    effective_through_week: int | None
    endpoint_plan: tuple[DataRefreshPlanItemResponse, ...]
    trigger_source: str
    status: RefreshStatus
    code_version: str
    normalizer_version: str
    started_at: datetime
    completed_at: datetime | None
    attempt_count: int
    succeeded_scope_count: int
    failed_scope_count: int

    @classmethod
    def from_resource(cls, refresh: RefreshRun) -> "DataRefreshAuditResponse":
        return cls(
            refresh_run_id=refresh.id,
            competition_id=refresh.competition_id,
            competition_season_id=refresh.competition_season_id,
            requested_through_week=refresh.requested_through_week,
            effective_through_week=refresh.effective_through_week,
            endpoint_plan=tuple(
                DataRefreshPlanItemResponse(
                    scope_key=item.scope_key,
                    endpoint_kind=item.endpoint_kind,
                    required=item.required,
                    dependency_scope_keys=item.dependency_scope_keys,
                )
                for item in refresh.endpoint_plan
            ),
            trigger_source=refresh.trigger_source,
            status=refresh.status,
            code_version=refresh.code_version,
            normalizer_version=refresh.normalizer_version,
            started_at=refresh.started_at,
            completed_at=refresh.completed_at,
            attempt_count=refresh.attempt_count,
            succeeded_scope_count=refresh.succeeded_scope_count,
            failed_scope_count=refresh.failed_scope_count,
        )


class DataRequestAuditResponse(BaseModel):
    """Stored request audit without raw payload, storage, or request parameters."""

    api_request_id: UUID
    refresh_run_id: UUID
    endpoint_kind: str
    scope_key: str
    week: int | None
    bracket_kind: str | None
    requested_at: datetime
    completed_at: datetime
    latency_ms: int | None
    status: RequestStatus
    http_status: int | None
    is_complete: bool
    completeness_reason: str | None
    response_sha256: str | None
    normalization_status: NormalizationStatus
    normalizer_version: str | None
    normalized_at: datetime | None
    error_code: str | None

    @classmethod
    def from_resource(cls, request: ApiRequest) -> "DataRequestAuditResponse":
        raw_error_code = request.error.get("code") if request.error else None
        return cls(
            api_request_id=request.id,
            refresh_run_id=request.refresh_run_id,
            endpoint_kind=request.endpoint_kind,
            scope_key=request.scope_key,
            week=request.week,
            bracket_kind=request.bracket_kind,
            requested_at=request.requested_at,
            completed_at=request.completed_at,
            latency_ms=request.latency_ms,
            status=request.status,
            http_status=request.http_status,
            is_complete=request.is_complete,
            completeness_reason=request.completeness_reason,
            response_sha256=request.response_sha256,
            normalization_status=request.normalization_status,
            normalizer_version=request.normalizer_version,
            normalized_at=request.normalized_at,
            error_code=(raw_error_code if isinstance(raw_error_code, str) else None),
        )


class DataRequestAuditPageResponse(BaseModel):
    items: tuple[DataRequestAuditResponse, ...]
    limit: int
    offset: int
    total: int

    @classmethod
    def from_resource(
        cls,
        page: Page[ApiRequest],
    ) -> "DataRequestAuditPageResponse":
        return cls(
            items=tuple(DataRequestAuditResponse.from_resource(item) for item in page.items),
            limit=page.limit,
            offset=page.offset,
            total=page.total,
        )
