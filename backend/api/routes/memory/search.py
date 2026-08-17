"""Revision-pinned hydrated memory search route."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_memory_api_dependencies
from backend.api.routes.memory.common import MemoryApiModel
from backend.composition import MemoryApiDependencies
from backend.resources.memory.search_documents import SearchDocumentQuery
from backend.services.memory import (
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
)


class MemorySearchRequest(MemoryApiModel):
    revision_id: UUID
    query: SearchDocumentQuery
    expand_exact_references: bool = False
    expand_stable_references: bool = False

    def retrieval_request(self) -> MemoryRetrievalRequest:
        return MemoryRetrievalRequest(
            query=self.query,
            expand_exact_references=self.expand_exact_references,
            expand_stable_references=self.expand_stable_references,
        )


class MemorySearchResponse(MemoryApiModel):
    result: MemoryRetrievalResult

router = APIRouter()
MemoryDependencies = Annotated[
    MemoryApiDependencies,
    Depends(get_memory_api_dependencies),
]


@router.post("/search", response_model=MemorySearchResponse)
def search_memory(
    competition_id: UUID,
    request: MemorySearchRequest,
    memory: MemoryDependencies,
) -> MemorySearchResponse:
    return MemorySearchResponse(
        result=memory.retrieval.search(
            competition_id=competition_id,
            revision_id=request.revision_id,
            request=request.retrieval_request(),
        )
    )
