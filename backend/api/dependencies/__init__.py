"""FastAPI dependency providers."""

from backend.api.dependencies.generations import (
    authorize_local_competition,
    get_generation_api_dependencies,
)
from backend.api.dependencies.memory import (
    get_correlation_id,
    get_memory_api_dependencies,
)
from backend.api.dependencies.services import get_api_runtime

__all__ = [
    "authorize_local_competition",
    "get_api_runtime",
    "get_correlation_id",
    "get_generation_api_dependencies",
    "get_memory_api_dependencies",
]
