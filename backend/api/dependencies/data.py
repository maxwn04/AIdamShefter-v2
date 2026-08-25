"""Competition-scoped dependency composition for data routes."""

from collections.abc import Iterator
from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends

from backend.api.dependencies.memory import get_correlation_id
from backend.api.dependencies.services import get_api_runtime
from backend.composition import (
    ApiRuntimeDependencies,
    DataApiDependencies,
    DataApiRuntimeDependencies,
    build_data_api_dependencies,
)
from backend.resources.context import CompetitionScope, LocalUserActor, ManagerContext


def get_data_api_dependencies(
    competition_id: UUID,
    correlation_id: Annotated[UUID, Depends(get_correlation_id)],
    runtime: Annotated[ApiRuntimeDependencies, Depends(get_api_runtime)],
) -> Iterator[DataApiDependencies]:
    """Build and close one request's local-user data boundary."""

    data_runtime = cast(DataApiRuntimeDependencies, runtime)
    context = ManagerContext[CompetitionScope](
        actor=LocalUserActor(),
        scope=CompetitionScope(competition_id=competition_id),
        correlation_id=correlation_id,
    )
    dependencies = build_data_api_dependencies(
        data_runtime.session_factory,
        context,
    )
    try:
        yield dependencies
    finally:
        dependencies.close()


__all__ = ["get_data_api_dependencies"]
