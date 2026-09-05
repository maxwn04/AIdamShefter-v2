"""Stable HTTP translation for datalayer application failures."""

from typing import Literal
from uuid import UUID

from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.services.datalayer import (
    DatalayerError,
    DatalayerResourceNotFound,
    DatalayerScopeConflict,
    EndpointPayloadRejected,
    InternalDatalayerFailure,
    InvalidDatalayerRequest,
    RefreshUnavailable,
    RosterIdentityMappingRequired,
    SnapshotInputsUnavailable,
    SnapshotUnavailable,
)
from backend.services.datalayer.snapshot_sqlite import SnapshotArtifactInvalid


DataErrorCode = Literal[
    "invalid_data_request",
    "data_resource_not_found",
    "data_scope_conflict",
    "endpoint_payload_rejected",
    "refresh_unavailable",
    "roster_identity_mapping_required",
    "snapshot_artifact_invalid",
    "snapshot_inputs_unavailable",
    "snapshot_unavailable",
    "datalayer_internal_failure",
]


class DataErrorDetail(BaseModel):
    code: DataErrorCode
    summary: str
    correlation_id: str | None = None
    competition_season_id: UUID | None = None
    sleeper_roster_ids: tuple[str, ...] | None = None
    missing_scopes: tuple[str, ...] | None = None
    claim_id: UUID | None = None
    refresh_run_id: UUID | None = None
    retryable: bool | None = None


class DataErrorResponse(BaseModel):
    error: DataErrorDetail


async def datalayer_error_handler(
    request: Request,
    error: Exception,
) -> JSONResponse:
    if not isinstance(error, DatalayerError):
        raise TypeError("datalayer error handler received a non-datalayer exception")
    status_code, code, summary = _http_error(error)
    correlation_id = (
        error.correlation_id
        if isinstance(error, InternalDatalayerFailure)
        else request.headers.get("X-Correlation-ID")
    )
    payload = DataErrorResponse(
        error=DataErrorDetail(
            code=code,
            summary=summary,
            correlation_id=correlation_id,
            **_error_fields(error),
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(payload, exclude_none=True),
    )


def _http_error(error: DatalayerError) -> tuple[int, DataErrorCode, str]:
    if isinstance(error, InvalidDatalayerRequest):
        return status.HTTP_400_BAD_REQUEST, "invalid_data_request", error.message
    if isinstance(error, DatalayerResourceNotFound):
        return (
            status.HTTP_404_NOT_FOUND,
            "data_resource_not_found",
            f"{error.resource_kind.replace('_', ' ')} was not found",
        )
    if isinstance(error, RosterIdentityMappingRequired):
        return (
            status.HTTP_409_CONFLICT,
            "roster_identity_mapping_required",
            error.message,
        )
    if isinstance(error, DatalayerScopeConflict):
        return status.HTTP_409_CONFLICT, "data_scope_conflict", error.message
    if isinstance(error, EndpointPayloadRejected):
        return (
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "endpoint_payload_rejected",
            error.summary,
        )
    if isinstance(error, SnapshotInputsUnavailable):
        return (
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "snapshot_inputs_unavailable",
            error.message,
        )
    if isinstance(error, RefreshUnavailable):
        return (
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "refresh_unavailable",
            str(error),
        )
    if isinstance(error, SnapshotUnavailable):
        return (
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "snapshot_unavailable",
            error.message,
        )
    if isinstance(error, SnapshotArtifactInvalid):
        return (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "snapshot_artifact_invalid",
            "snapshot artifact verification failed",
        )
    if isinstance(error, InternalDatalayerFailure):
        return (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "datalayer_internal_failure",
            "the datalayer operation failed unexpectedly",
        )
    raise TypeError(f"unsupported datalayer error {type(error).__name__}")


def _error_fields(error: DatalayerError) -> dict[str, object]:
    if isinstance(error, RosterIdentityMappingRequired):
        return {
            "competition_season_id": error.competition_season_id,
            "sleeper_roster_ids": error.sleeper_roster_ids,
        }
    if isinstance(error, SnapshotInputsUnavailable):
        return {
            "competition_season_id": error.competition_season_id,
            "missing_scopes": tuple(scope.value for scope in error.missing_scopes),
        }
    if isinstance(error, RefreshUnavailable):
        return {
            "competition_season_id": error.competition_season_id,
            "claim_id": error.claim_id,
            "refresh_run_id": error.refresh_run_id,
            "retryable": error.retryable,
        }
    return {}


__all__ = ["DataErrorResponse", "datalayer_error_handler"]
