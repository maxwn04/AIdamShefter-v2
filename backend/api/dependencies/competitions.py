"""Dependency composition for competition and season product routes."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends

from backend.api.dependencies.memory import get_correlation_id
from backend.api.dependencies.services import get_api_runtime
from backend.composition import (
    ApiRuntimeDependencies,
    CompetitionApiRuntimeDependencies,
    CompetitionCatalogDependencies,
    CompetitionSeasonDependencies,
    build_competition_catalog_dependencies,
    build_competition_season_dependencies,
)
from backend.resources.context import (
    CompetitionScope,
    GlobalScope,
    LocalUserActor,
    ManagerContext,
)


def get_competition_catalog_dependencies(
    correlation_id: Annotated[UUID, Depends(get_correlation_id)],
    runtime: Annotated[ApiRuntimeDependencies, Depends(get_api_runtime)],
) -> CompetitionCatalogDependencies:
    """Build one request's global local-user competition boundary."""

    core_runtime = cast(CompetitionApiRuntimeDependencies, runtime)
    context = ManagerContext[GlobalScope](
        actor=LocalUserActor(),
        scope=GlobalScope(reason="manage competition catalog"),
        correlation_id=correlation_id,
    )
    return build_competition_catalog_dependencies(
        core_runtime.session_factory,
        context,
    )


def get_competition_season_dependencies(
    competition_id: UUID,
    correlation_id: Annotated[UUID, Depends(get_correlation_id)],
    runtime: Annotated[ApiRuntimeDependencies, Depends(get_api_runtime)],
) -> CompetitionSeasonDependencies:
    """Build one request's competition-scoped season boundary."""

    core_runtime = cast(CompetitionApiRuntimeDependencies, runtime)
    context = ManagerContext[CompetitionScope](
        actor=LocalUserActor(),
        scope=CompetitionScope(competition_id=competition_id),
        correlation_id=correlation_id,
    )
    return build_competition_season_dependencies(
        core_runtime.session_factory,
        context,
    )


__all__ = [
    "get_competition_catalog_dependencies",
    "get_competition_season_dependencies",
]
