"""Trigger read and complete-replacement routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import Field

from backend.api.dependencies import get_memory_api_dependencies
from backend.api.routes.memory.common import MemoryApiModel, MemoryMutationResponse
from backend.composition import MemoryApiDependencies
from backend.resources.memory.triggers import Trigger, TriggerContent
from backend.services.memory import MemoryMutationMetadata, MemoryMutationOrigin


class TriggerCreateRequest(MemoryApiModel):
    origin: MemoryMutationOrigin
    content: TriggerContent
    metadata: MemoryMutationMetadata = Field(default_factory=MemoryMutationMetadata)


class TriggerReplaceRequest(TriggerCreateRequest):
    expected_item_revision: int = Field(gt=0, strict=True)


class TriggerResponse(MemoryApiModel):
    memory: Trigger


class TriggerHistoryResponse(MemoryApiModel):
    items: tuple[Trigger, ...]

router = APIRouter(prefix="/triggers")
MemoryDependencies = Annotated[
    MemoryApiDependencies,
    Depends(get_memory_api_dependencies),
]


@router.get("/versions/{version_id}", response_model=TriggerResponse)
def exact_trigger(version_id: UUID, memory: MemoryDependencies) -> TriggerResponse:
    return TriggerResponse(memory=memory.triggers.exact(version_id))


@router.get("/{item_id}/history", response_model=TriggerHistoryResponse)
def trigger_history(item_id: UUID, memory: MemoryDependencies) -> TriggerHistoryResponse:
    return TriggerHistoryResponse(items=memory.triggers.history(item_id))


@router.post(
    "",
    response_model=MemoryMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_trigger(
    request: TriggerCreateRequest,
    memory: MemoryDependencies,
) -> MemoryMutationResponse:
    return MemoryMutationResponse(
        result=memory.mutations.create_trigger(
            request.origin,
            request.content,
            metadata=request.metadata,
        )
    )


@router.put("/{item_id}", response_model=MemoryMutationResponse)
def replace_trigger(
    item_id: UUID,
    request: TriggerReplaceRequest,
    memory: MemoryDependencies,
) -> MemoryMutationResponse:
    return MemoryMutationResponse(
        result=memory.mutations.replace_trigger(
            request.origin,
            item_id,
            request.expected_item_revision,
            request.content,
            metadata=request.metadata,
        )
    )
