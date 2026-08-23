"""Competition-scoped generation dependency composition."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends

from backend.api.dependencies.memory import get_correlation_id
from backend.api.dependencies.services import get_api_runtime
from backend.composition import (
    ApiRuntimeDependencies,
    GenerationDependencies,
    GenerationRuntimeDependencies,
    build_generation_dependencies,
)
from backend.resources.context import CompetitionScope, LocalUserActor, ManagerContext


def authorize_local_competition(competition_id: UUID) -> UUID:
    """Explicit local-product authorization seam for one competition."""

    return competition_id


def get_generation_api_dependencies(
    competition_id: Annotated[UUID, Depends(authorize_local_competition)],
    correlation_id: Annotated[UUID, Depends(get_correlation_id)],
    runtime: Annotated[ApiRuntimeDependencies, Depends(get_api_runtime)],
) -> GenerationDependencies:
    """Build one request's local-user generation boundary."""

    generation_runtime = cast(GenerationRuntimeDependencies, runtime)
    context = ManagerContext[CompetitionScope](
        actor=LocalUserActor(),
        scope=CompetitionScope(competition_id=competition_id),
        correlation_id=correlation_id,
    )
    return build_generation_dependencies(
        generation_runtime.session_factory,
        context,
    )

