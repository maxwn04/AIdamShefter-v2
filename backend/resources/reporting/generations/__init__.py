"""Public durable generation resource contract."""

from backend.resources.reporting.generations.errors import (
    GenerationConcurrencyConflict,
    GenerationLifecycleConflict,
    GenerationResourceError,
    GenerationResourceNotFound,
)
from backend.resources.reporting.generations.manager import GenerationManager
from backend.resources.reporting.generations.objects import (
    CancelGeneration,
    CreateGeneration,
    FailGeneration,
    Generation,
    GenerationDetail,
    GenerationKind,
    GenerationPage,
    GenerationQuery,
    GenerationStatus,
    GenerationSummary,
    StartGeneration,
    SucceedGeneration,
    UpdateGenerationProgress,
)

__all__ = [
    "CancelGeneration",
    "CreateGeneration",
    "FailGeneration",
    "Generation",
    "GenerationConcurrencyConflict",
    "GenerationDetail",
    "GenerationKind",
    "GenerationLifecycleConflict",
    "GenerationManager",
    "GenerationPage",
    "GenerationQuery",
    "GenerationResourceError",
    "GenerationResourceNotFound",
    "GenerationStatus",
    "GenerationSummary",
    "StartGeneration",
    "SucceedGeneration",
    "UpdateGenerationProgress",
]
