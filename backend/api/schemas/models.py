"""Transport models for configured model selection."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from backend.services.model_usage import ModelCatalogItem


class ModelCatalogResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    models: tuple[ModelCatalogItem, ...]
