"""Competition-scoped dependency composition for memory routes."""

from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import Depends, Header

from backend.api.dependencies.services import get_api_runtime
from backend.composition import (
    ApiRuntimeDependencies,
    MemoryApiDependencies,
    MemoryApiRuntimeDependencies,
    build_memory_api_dependencies,
)
from backend.resources.context import (
    CompetitionScope,
    LocalUserActor,
    ManagerContext,
)


def get_correlation_id(
    correlation_id: Annotated[
        UUID | None,
        Header(alias="X-Correlation-ID"),
    ] = None,
) -> UUID:
    """Use a caller correlation ID when supplied, otherwise create one."""

    return correlation_id or uuid4()


def get_memory_api_dependencies(
    competition_id: UUID,
    correlation_id: Annotated[UUID, Depends(get_correlation_id)],
    runtime: Annotated[ApiRuntimeDependencies, Depends(get_api_runtime)],
) -> MemoryApiDependencies:
    """Build one request's local-user memory boundary."""

    memory_runtime = cast(MemoryApiRuntimeDependencies, runtime)
    context = ManagerContext[CompetitionScope](
        actor=LocalUserActor(),
        scope=CompetitionScope(competition_id=competition_id),
        correlation_id=correlation_id,
    )
    return build_memory_api_dependencies(memory_runtime.session_factory, context)
