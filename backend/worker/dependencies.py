"""Worker-owned generation dependency composition."""

from uuid import UUID, uuid4

from backend.composition import (
    GenerationDependencies,
    GenerationRuntimeDependencies,
    build_generation_dependencies,
)
from backend.resources.context import (
    CompetitionScope,
    ManagerContext,
    SystemProcessActor,
)
from backend.resources.sleeper_data.refreshes import RefreshRunManager


def build_worker_generation_dependencies(
    runtime: GenerationRuntimeDependencies,
    competition_id: UUID,
    *,
    correlation_id: UUID | None = None,
) -> GenerationDependencies:
    """Build the same scoped generation service used by the HTTP boundary."""

    context = ManagerContext[CompetitionScope](
        actor=SystemProcessActor(process_name="generation-worker"),
        scope=CompetitionScope(competition_id=competition_id),
        correlation_id=correlation_id or uuid4(),
    )
    return build_generation_dependencies(runtime.session_factory, context)


def build_worker_refresh_manager(
    runtime: GenerationRuntimeDependencies,
    competition_id: UUID,
    *,
    correlation_id: UUID | None = None,
) -> RefreshRunManager:
    """Build a scoped refresh manager for explicit worker recovery."""

    context = ManagerContext[CompetitionScope](
        actor=SystemProcessActor(process_name="refresh-recovery-worker"),
        scope=CompetitionScope(competition_id=competition_id),
        correlation_id=correlation_id or uuid4(),
    )
    return RefreshRunManager(runtime.session_factory, context)

