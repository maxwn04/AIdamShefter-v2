"""Immutable, storage-independent datalayer workflow values."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend.services.datalayer.sleeper.scope import ScopeKey


class _WorkflowValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


WarningCode = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    ),
]

WarningSummary = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


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
    through_week: int | None = Field(default=None, ge=1, le=18, strict=True)
    trigger: RefreshTrigger


class ScopeRefreshResult(_WorkflowValue):
    scope_key: ScopeKey
    api_request_id: UUID
    fetch_status: RequestStatus
    normalization_status: NormalizationStatus
    changed_current_view: bool = Field(strict=True)
    warning_codes: tuple[WarningCode, ...] = ()


class RefreshOutcome(_WorkflowValue):
    refresh_run_id: UUID
    status: RefreshStatus
    requested_scope_count: int = Field(ge=0, strict=True)
    succeeded_scope_count: int = Field(ge=0, strict=True)
    failed_scope_count: int = Field(ge=0, strict=True)
    scope_results: tuple[ScopeRefreshResult, ...]


class SnapshotRequest(_WorkflowValue):
    competition_season_id: UUID
    through_week: int = Field(ge=1, le=18, strict=True)
    as_of_date: date


class CompletenessWarning(_WorkflowValue):
    """Safe structured warning retained with a snapshot or workflow result."""

    code: WarningCode
    summary: WarningSummary
    scope_key: ScopeKey | None = None
