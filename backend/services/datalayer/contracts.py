"""Stable workflow values shared by datalayer services and workers."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .sleeper.scope import ScopeKey


class _WorkflowValue(BaseModel):
    model_config = ConfigDict(frozen=True)


class RefreshTrigger(StrEnum):
    MANUAL = "manual"
    GENERATION = "generation"
    SCHEDULED = "scheduled"
    BACKFILL = "backfill"


class RefreshStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RequestStatus(StrEnum):
    SUCCEEDED = "succeeded"
    HTTP_ERROR = "http_error"
    TRANSPORT_ERROR = "transport_error"
    INVALID_PAYLOAD = "invalid_payload"


class NormalizationStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    NOT_APPLICABLE = "not_applicable"


class ApplyDisposition(StrEnum):
    APPLIED = "applied"
    STALE_IGNORED = "stale_ignored"
    ALREADY_APPLIED = "already_applied"
    IDENTICAL_HEAD_ADVANCED = "identical_head_advanced"


class RefreshRequest(_WorkflowValue):
    competition_season_id: UUID
    through_week: int | None = Field(default=None, ge=1, le=18)
    trigger: RefreshTrigger


class ScopeRefreshResult(_WorkflowValue):
    scope_key: ScopeKey
    api_request_id: UUID
    fetch_status: RequestStatus
    normalization_status: NormalizationStatus
    changed_current_view: bool
    warning_codes: tuple[str, ...] = ()


class RefreshOutcome(_WorkflowValue):
    refresh_run_id: UUID
    status: RefreshStatus
    requested_scope_count: int = Field(ge=0)
    succeeded_scope_count: int = Field(ge=0)
    failed_scope_count: int = Field(ge=0)
    scope_results: tuple[ScopeRefreshResult, ...]


class SnapshotRequest(_WorkflowValue):
    competition_season_id: UUID
    through_week: int = Field(ge=1, le=18)
    observed_through: datetime

    @field_validator("observed_through")
    @classmethod
    def require_aware_observation_boundary(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_through must include a timezone")
        return value
