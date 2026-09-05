"""Stable HTTP translation for typed memory application failures."""

from typing import Literal

from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.resources.memory.common import (
    CanonicalStateHashMismatchError,
    CrossCompetitionEntityReferenceError,
    CrossCompetitionReferenceError,
    DuplicateContextNoteError,
    EntityReferenceNotFoundError,
    GenerationMemoryContextClosedError,
    MemoryApplicationError,
    MemoryIdentityConflictError,
    RevisionNotFoundError,
    SearchProjectionHydrationError,
    StaleCanonicalRevisionError,
    StaleItemVersionError,
    TargetNotFoundError,
    WrongTargetKindError,
)

from backend.resources.memory.triggers.validation import InvalidTradeOriginError

MemoryErrorCode = Literal[
    "canonical_state_inconsistent",
    "context_note_conflict",
    "cross_competition_entity",
    "cross_competition_reference",
    "generation_memory_closed",
    "invalid_trigger_origin",
    "memory_identity_conflict",
    "revision_not_found",
    "search_projection_inconsistent",
    "stale_canonical_revision",
    "stale_item_version",
    "target_not_found",
    "wrong_target_kind",
]


class MemoryErrorDetail(BaseModel):
    code: MemoryErrorCode
    message: str


class MemoryErrorResponse(BaseModel):
    detail: MemoryErrorDetail


async def memory_application_error_handler(
    _request: Request,
    error: Exception,
) -> JSONResponse:
    """Return a stable, safe status and code for a typed memory failure."""

    if not isinstance(error, MemoryApplicationError):
        raise TypeError("memory error handler received a non-memory exception")
    status_code, code, message = _http_error(error)
    payload = MemoryErrorResponse(
        detail=MemoryErrorDetail(code=code, message=message)
    )
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(payload),
    )


def _http_error(error: MemoryApplicationError) -> tuple[int, MemoryErrorCode, str]:
    if isinstance(error, InvalidTradeOriginError):
        return status.HTTP_400_BAD_REQUEST, "invalid_trigger_origin", str(error)
    if isinstance(error, RevisionNotFoundError):
        return status.HTTP_404_NOT_FOUND, "revision_not_found", str(error)
    if isinstance(error, (TargetNotFoundError, EntityReferenceNotFoundError)):
        return status.HTTP_404_NOT_FOUND, "target_not_found", str(error)
    if isinstance(error, DuplicateContextNoteError):
        return status.HTTP_409_CONFLICT, "context_note_conflict", str(error)
    if isinstance(error, MemoryIdentityConflictError):
        return status.HTTP_409_CONFLICT, "memory_identity_conflict", str(error)
    if isinstance(error, StaleItemVersionError):
        return status.HTTP_409_CONFLICT, "stale_item_version", str(error)
    if isinstance(error, StaleCanonicalRevisionError):
        return status.HTTP_409_CONFLICT, "stale_canonical_revision", str(error)
    if isinstance(error, WrongTargetKindError):
        return status.HTTP_400_BAD_REQUEST, "wrong_target_kind", str(error)
    if isinstance(error, CrossCompetitionReferenceError):
        return (
            status.HTTP_400_BAD_REQUEST,
            "cross_competition_reference",
            str(error),
        )
    if isinstance(error, CrossCompetitionEntityReferenceError):
        return (
            status.HTTP_400_BAD_REQUEST,
            "cross_competition_entity",
            str(error),
        )
    if isinstance(error, GenerationMemoryContextClosedError):
        return status.HTTP_409_CONFLICT, "generation_memory_closed", str(error)
    if isinstance(error, SearchProjectionHydrationError):
        return (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "search_projection_inconsistent",
            "memory search projection is inconsistent with canonical memory",
        )
    if isinstance(error, CanonicalStateHashMismatchError):
        return (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "canonical_state_inconsistent",
            "canonical memory state verification failed",
        )
    raise TypeError(f"unsupported memory application error {type(error).__name__}")
