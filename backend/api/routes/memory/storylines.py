"""Storyline read and complete-replacement routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import Field

from backend.api.dependencies import get_memory_api_dependencies
from backend.api.routes.memory.common import MemoryApiModel, MemoryMutationResponse
from backend.composition import MemoryApiDependencies
from backend.resources.memory.storylines import Storyline, StorylineContent
from backend.services.memory import MemoryMutationMetadata, MemoryMutationOrigin


class StorylineCreateRequest(MemoryApiModel):
    origin: MemoryMutationOrigin
    content: StorylineContent
    metadata: MemoryMutationMetadata = Field(default_factory=MemoryMutationMetadata)


class StorylineReplaceRequest(StorylineCreateRequest):
    expected_item_revision: int = Field(gt=0, strict=True)


class StorylineResponse(MemoryApiModel):
    memory: Storyline


class StorylineHistoryResponse(MemoryApiModel):
    items: tuple[Storyline, ...]

router = APIRouter(prefix="/storylines")
MemoryDependencies = Annotated[
    MemoryApiDependencies,
    Depends(get_memory_api_dependencies),
]


@router.get("/versions/{version_id}", response_model=StorylineResponse)
def exact_storyline(
    version_id: UUID,
    memory: MemoryDependencies,
) -> StorylineResponse:
    return StorylineResponse(memory=memory.storylines.exact(version_id))


@router.get("/{item_id}/history", response_model=StorylineHistoryResponse)
def storyline_history(
    item_id: UUID,
    memory: MemoryDependencies,
) -> StorylineHistoryResponse:
    return StorylineHistoryResponse(items=memory.storylines.history(item_id))


@router.post(
    "",
    response_model=MemoryMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_storyline(
    request: StorylineCreateRequest,
    memory: MemoryDependencies,
) -> MemoryMutationResponse:
    return MemoryMutationResponse(
        result=memory.mutations.create_storyline(
            request.origin,
            request.content,
            metadata=request.metadata,
        )
    )


@router.put("/{item_id}", response_model=MemoryMutationResponse)
def replace_storyline(
    item_id: UUID,
    request: StorylineReplaceRequest,
    memory: MemoryDependencies,
) -> MemoryMutationResponse:
    return MemoryMutationResponse(
        result=memory.mutations.replace_storyline(
            request.origin,
            item_id,
            request.expected_item_revision,
            request.content,
            metadata=request.metadata,
        )
    )
