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

