"""Configured model-selection catalog."""

from backend.config import ModelCatalogSettings
from backend.services.model_usage.objects import ModelCatalog, ModelCatalogItem
from backend.services.model_usage.pricing import LiteLLMModelRegistry


class ModelCatalogService:
    def __init__(
        self,
        settings: ModelCatalogSettings,
        registry: LiteLLMModelRegistry,
    ) -> None:
        self._settings = settings
        self._registry = registry

    def list(self) -> ModelCatalog:
        items: list[ModelCatalogItem] = []
        for model in self._settings.model_chain():
            info = self._registry.model_info(model)
            items.append(
                ModelCatalogItem(
                    provider=self._registry.provider_for(model),
                    model=model,
                    display_name=model.rsplit("/", 1)[-1],
                    is_default=model == self._settings.primary_model,
                    supports_reasoning=bool(
                        info is not None and info.get("supports_reasoning") is True
                    ),
                )
            )
        return ModelCatalog(models=tuple(items))
