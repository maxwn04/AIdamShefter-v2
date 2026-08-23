"""Stable HTTP translation for reporting resource failures."""

from typing import Literal

from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.resources.reporting.ai_calls import (
    AICallConcurrencyConflict,
    AICallLifecycleConflict,
    AICallResourceNotFound,
)
from backend.resources.reporting.artifact_versions import (
    ArtifactVersionConcurrencyConflict,
    ArtifactVersionLifecycleConflict,
    ArtifactVersionProvenanceConflict,
    ArtifactVersionResourceNotFound,
)
from backend.resources.reporting.artifacts import (
    ArtifactConcurrencyConflict,
    ArtifactLifecycleConflict,
    ArtifactMediaTypeConflict,
    ArtifactResourceNotFound,
)
from backend.resources.reporting.generations import (
    GenerationConcurrencyConflict,
    GenerationLifecycleConflict,
    GenerationResourceNotFound,
)
from backend.resources.reporting.tool_calls import (
    ToolCallConcurrencyConflict,
    ToolCallLifecycleConflict,
    ToolCallResourceNotFound,
)


ReportingErrorCode = Literal["reporting_conflict", "reporting_not_found"]
_NOT_FOUND = (
    GenerationResourceNotFound,
    AICallResourceNotFound,
    ToolCallResourceNotFound,
    ArtifactResourceNotFound,
    ArtifactVersionResourceNotFound,
)
_CONFLICT = (
    GenerationConcurrencyConflict,
    GenerationLifecycleConflict,
    AICallConcurrencyConflict,
    AICallLifecycleConflict,
    ToolCallConcurrencyConflict,
    ToolCallLifecycleConflict,
    ArtifactConcurrencyConflict,
    ArtifactLifecycleConflict,
    ArtifactMediaTypeConflict,
    ArtifactVersionConcurrencyConflict,
    ArtifactVersionLifecycleConflict,
    ArtifactVersionProvenanceConflict,
)
REPORTING_APPLICATION_ERRORS = (*_NOT_FOUND, *_CONFLICT)


class ReportingErrorDetail(BaseModel):
    code: ReportingErrorCode
    message: str


class ReportingErrorResponse(BaseModel):
    detail: ReportingErrorDetail


async def reporting_application_error_handler(
    _request: Request,
    error: Exception,
) -> JSONResponse:
    if isinstance(error, _NOT_FOUND):
        status_code = status.HTTP_404_NOT_FOUND
        code: ReportingErrorCode = "reporting_not_found"
        message = str(error)
    elif isinstance(error, _CONFLICT):
        status_code = status.HTTP_409_CONFLICT
        code = "reporting_conflict"
        message = str(error)
    else:
        raise TypeError("reporting error handler received an unsupported exception")
    payload = ReportingErrorResponse(
        detail=ReportingErrorDetail(code=code, message=message)
    )
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))

