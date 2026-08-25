"""Stable HTTP translation for datalayer application failures."""

from typing import Literal

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
    SnapshotUnavailable,
)


DataErrorCode = Literal[
    "invalid_data_request",
    "data_resource_not_found",
    "data_scope_conflict",
    "endpoint_payload_rejected",
    "snapshot_unavailable",
    "datalayer_internal_failure",
]


class DataErrorDetail(BaseModel):
    code: DataErrorCode
    summary: str
    correlation_id: str | None = None


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
    if isinstance(error, DatalayerScopeConflict):
        return status.HTTP_409_CONFLICT, "data_scope_conflict", error.message
    if isinstance(error, EndpointPayloadRejected):
        return (
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "endpoint_payload_rejected",
            error.summary,
        )
    if isinstance(error, SnapshotUnavailable):
        return (
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "snapshot_unavailable",
            error.message,
        )
    if isinstance(error, InternalDatalayerFailure):
        return (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "datalayer_internal_failure",
            "the datalayer operation failed unexpectedly",
        )
    raise TypeError(f"unsupported datalayer error {type(error).__name__}")


__all__ = ["DataErrorResponse", "datalayer_error_handler"]
