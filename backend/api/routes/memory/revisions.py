"""Canonical revision read routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_memory_api_dependencies
from backend.api.routes.memory.common import MemoryApiModel
from backend.composition import MemoryApiDependencies
from backend.resources.memory.revisions import CanonicalRevision


class RevisionResponse(MemoryApiModel):
    revision: CanonicalRevision


class RevisionHistoryResponse(MemoryApiModel):
    revisions: tuple[CanonicalRevision, ...]

router = APIRouter(prefix="/revisions")
MemoryDependencies = Annotated[
    MemoryApiDependencies,
    Depends(get_memory_api_dependencies),
]


@router.get("/current", response_model=RevisionResponse)
def current_revision(memory: MemoryDependencies) -> RevisionResponse:
    return RevisionResponse(revision=memory.revisions.current())


@router.get("", response_model=RevisionHistoryResponse)
def revision_history(memory: MemoryDependencies) -> RevisionHistoryResponse:
    return RevisionHistoryResponse(revisions=memory.revisions.history())


@router.get("/{revision_id}", response_model=RevisionResponse)
def exact_revision(
    revision_id: UUID,
    memory: MemoryDependencies,
) -> RevisionResponse:
    return RevisionResponse(revision=memory.revisions.pin(revision_id))
