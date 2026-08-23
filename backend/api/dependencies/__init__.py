"""FastAPI dependency providers."""

from backend.api.dependencies.competitions import (
    get_competition_catalog_dependencies,
    get_competition_season_dependencies,
)
from backend.api.dependencies.data import get_data_api_dependencies
from backend.api.dependencies.generations import (
    authorize_local_competition,
    get_generation_api_dependencies,
)
from backend.api.dependencies.memory import (
    get_correlation_id,
    get_memory_api_dependencies,
)
from backend.api.dependencies.models import get_model_catalog
from backend.api.dependencies.services import get_api_runtime
from backend.api.dispatch import get_generation_dispatcher

__all__ = [
    "authorize_local_competition",
    "get_api_runtime",
    "get_competition_catalog_dependencies",
    "get_competition_season_dependencies",
    "get_data_api_dependencies",
    "get_correlation_id",
    "get_generation_api_dependencies",
    "get_generation_dispatcher",
    "get_memory_api_dependencies",
    "get_model_catalog",
]
