"""Shared one-generation worker execution boundary."""

from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from backend.composition import (
    GenerationDependencies,
    GenerationRuntimeDependencies,
    build_worker_runtime,
)
from backend.services.generations import GenerationExecutionResult
from backend.worker.dependencies import build_worker_generation_dependencies


RuntimeFactory = Callable[[], GenerationRuntimeDependencies]


class DependencyFactory(Protocol):
    def __call__(
        self,
        runtime: GenerationRuntimeDependencies,
        competition_id: UUID,
        *,
        correlation_id: UUID | None = None,
    ) -> GenerationDependencies: ...


async def execute_one_generation(
    competition_id: UUID,
    generation_id: UUID,
    *,
    runtime_factory: RuntimeFactory = build_worker_runtime,
    dependency_factory: DependencyFactory = build_worker_generation_dependencies,
) -> GenerationExecutionResult:
    """Execute one generation with worker credentials and deterministic cleanup."""

    runtime = runtime_factory()
    try:
        runtime.assert_ready()
        dependencies = dependency_factory(runtime, competition_id)
        return await dependencies.service.execute(generation_id)
    finally:
        runtime.close()
