"""Configured model-selection routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_model_catalog
from backend.api.schemas.models import ModelCatalogResponse
from backend.services.model_usage import ModelCatalogService


router = APIRouter(tags=["models"])
ModelCatalogDependency = Annotated[ModelCatalogService, Depends(get_model_catalog)]


@router.get("/models", response_model=ModelCatalogResponse)
def model_catalog(catalog: ModelCatalogDependency) -> ModelCatalogResponse:
    return ModelCatalogResponse(models=catalog.list().models)
