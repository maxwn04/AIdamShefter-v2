"""Fact read and complete-replacement routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import Field

from backend.api.dependencies import get_memory_api_dependencies
from backend.api.routes.memory.common import MemoryApiModel, MemoryMutationResponse
from backend.composition import MemoryApiDependencies
from backend.resources.memory.facts import Fact, FactContent
from backend.services.memory import MemoryMutationMetadata, MemoryMutationOrigin


class FactCreateRequest(MemoryApiModel):
    origin: MemoryMutationOrigin
    content: FactContent
    metadata: MemoryMutationMetadata = Field(default_factory=MemoryMutationMetadata)


class FactReplaceRequest(FactCreateRequest):
    expected_item_revision: int = Field(gt=0, strict=True)


class FactResponse(MemoryApiModel):
    memory: Fact


class FactHistoryResponse(MemoryApiModel):
    items: tuple[Fact, ...]

router = APIRouter(prefix="/facts")
MemoryDependencies = Annotated[
    MemoryApiDependencies,
    Depends(get_memory_api_dependencies),
]


@router.get("/versions/{version_id}", response_model=FactResponse)
def exact_fact(version_id: UUID, memory: MemoryDependencies) -> FactResponse:
    return FactResponse(memory=memory.facts.exact(version_id))


@router.get("/{item_id}/history", response_model=FactHistoryResponse)
def fact_history(item_id: UUID, memory: MemoryDependencies) -> FactHistoryResponse:
    return FactHistoryResponse(items=memory.facts.history(item_id))


@router.post(
    "",
    response_model=MemoryMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_fact(
    request: FactCreateRequest,
    memory: MemoryDependencies,
) -> MemoryMutationResponse:
    return MemoryMutationResponse(
        result=memory.mutations.create_fact(
            request.origin,
            request.content,
            metadata=request.metadata,
        )
    )


@router.put("/{item_id}", response_model=MemoryMutationResponse)
def replace_fact(
    item_id: UUID,
    request: FactReplaceRequest,
    memory: MemoryDependencies,
) -> MemoryMutationResponse:
    return MemoryMutationResponse(
        result=memory.mutations.replace_fact(
            request.origin,
            item_id,
            request.expected_item_revision,
            request.content,
            metadata=request.metadata,
        )
    )
