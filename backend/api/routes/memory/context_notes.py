"""Context-note read and complete-replacement routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import Field

from backend.api.dependencies import get_memory_api_dependencies
from backend.api.routes.memory.common import MemoryApiModel, MemoryMutationResponse
from backend.composition import MemoryApiDependencies
from backend.resources.memory.context_notes import (
    ContextNote,
    ContextNoteContent,
    ContextNoteIdentity,
)
from backend.services.memory import MemoryMutationMetadata, MemoryMutationOrigin


class ContextNoteCreateRequest(MemoryApiModel):
    origin: MemoryMutationOrigin
    identity: ContextNoteIdentity
    content: ContextNoteContent
    metadata: MemoryMutationMetadata = Field(default_factory=MemoryMutationMetadata)


class ContextNoteReplaceRequest(MemoryApiModel):
    origin: MemoryMutationOrigin
    expected_item_revision: int = Field(gt=0, strict=True)
    content: ContextNoteContent
    metadata: MemoryMutationMetadata = Field(default_factory=MemoryMutationMetadata)


class ContextNoteResponse(MemoryApiModel):
    memory: ContextNote


class ContextNoteHistoryResponse(MemoryApiModel):
    items: tuple[ContextNote, ...]

router = APIRouter(prefix="/context-notes")
MemoryDependencies = Annotated[
    MemoryApiDependencies,
    Depends(get_memory_api_dependencies),
]


@router.get("/versions/{version_id}", response_model=ContextNoteResponse)
def exact_context_note(
    version_id: UUID,
    memory: MemoryDependencies,
) -> ContextNoteResponse:
    return ContextNoteResponse(memory=memory.context_notes.exact(version_id))


@router.get("/{item_id}/history", response_model=ContextNoteHistoryResponse)
def context_note_history(
    item_id: UUID,
    memory: MemoryDependencies,
) -> ContextNoteHistoryResponse:
    return ContextNoteHistoryResponse(items=memory.context_notes.history(item_id))


@router.post(
    "",
    response_model=MemoryMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_context_note(
    request: ContextNoteCreateRequest,
    memory: MemoryDependencies,
) -> MemoryMutationResponse:
    return MemoryMutationResponse(
        result=memory.mutations.create_context_note(
            request.origin,
            request.identity,
            request.content,
            metadata=request.metadata,
        )
    )


@router.put("/{item_id}", response_model=MemoryMutationResponse)
def replace_context_note(
    item_id: UUID,
    request: ContextNoteReplaceRequest,
    memory: MemoryDependencies,
) -> MemoryMutationResponse:
    return MemoryMutationResponse(
        result=memory.mutations.replace_context_note(
            request.origin,
            item_id,
            request.expected_item_revision,
            request.content,
            metadata=request.metadata,
        )
    )
