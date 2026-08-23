"""Process-scoped configured model catalog dependency."""

from typing import Annotated, cast

from fastapi import Depends

from backend.api.dependencies.services import get_api_runtime
from backend.composition import ApiRuntimeDependencies, ModelApiRuntimeDependencies
from backend.services.model_usage import ModelCatalogService


def get_model_catalog(
    runtime: Annotated[ApiRuntimeDependencies, Depends(get_api_runtime)],
) -> ModelCatalogService:
    return cast(ModelApiRuntimeDependencies, runtime).model_catalog
