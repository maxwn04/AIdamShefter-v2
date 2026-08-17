"""Event read and complete-replacement routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import Field

from backend.api.dependencies import get_memory_api_dependencies
from backend.api.routes.memory.common import MemoryApiModel, MemoryMutationResponse
from backend.composition import MemoryApiDependencies
from backend.resources.memory.events import Event, EventContent
from backend.services.memory import MemoryMutationMetadata, MemoryMutationOrigin


class EventCreateRequest(MemoryApiModel):
    origin: MemoryMutationOrigin
    content: EventContent
    metadata: MemoryMutationMetadata = Field(default_factory=MemoryMutationMetadata)


class EventReplaceRequest(EventCreateRequest):
    expected_item_revision: int = Field(gt=0, strict=True)


class EventResponse(MemoryApiModel):
    memory: Event


class EventHistoryResponse(MemoryApiModel):
    items: tuple[Event, ...]

router = APIRouter(prefix="/events")
MemoryDependencies = Annotated[
    MemoryApiDependencies,
    Depends(get_memory_api_dependencies),
]


@router.get("/versions/{version_id}", response_model=EventResponse)
def exact_event(version_id: UUID, memory: MemoryDependencies) -> EventResponse:
    return EventResponse(memory=memory.events.exact(version_id))


@router.get("/{item_id}/history", response_model=EventHistoryResponse)
def event_history(item_id: UUID, memory: MemoryDependencies) -> EventHistoryResponse:
    return EventHistoryResponse(items=memory.events.history(item_id))


@router.post(
    "",
    response_model=MemoryMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_event(
    request: EventCreateRequest,
    memory: MemoryDependencies,
) -> MemoryMutationResponse:
    return MemoryMutationResponse(
        result=memory.mutations.create_event(
            request.origin,
            request.content,
            metadata=request.metadata,
        )
    )


@router.put("/{item_id}", response_model=MemoryMutationResponse)
def replace_event(
    item_id: UUID,
    request: EventReplaceRequest,
    memory: MemoryDependencies,
) -> MemoryMutationResponse:
    return MemoryMutationResponse(
        result=memory.mutations.replace_event(
            request.origin,
            item_id,
            request.expected_item_revision,
            request.content,
            metadata=request.metadata,
        )
    )
