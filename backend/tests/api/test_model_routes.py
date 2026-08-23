from collections.abc import Callable
from typing import final

from httpx import ASGITransport, AsyncClient
import pytest

from backend.api.app import create_app
from backend.api.dependencies import get_model_catalog
from backend.composition import ApiRuntimeDependencies
from backend.services.model_usage import ModelCatalog, ModelCatalogItem


@final
class StubRuntime:
    def assert_ready(self) -> None:
        pass

    def close(self) -> None:
        pass


def runtime_factory() -> Callable[[], ApiRuntimeDependencies]:
    return StubRuntime


class StubCatalog:
    def list(self) -> ModelCatalog:
        return ModelCatalog(
            models=(
                ModelCatalogItem(
                    provider="deepseek",
                    model="deepseek/deepseek-v4-pro",
                    display_name="deepseek-v4-pro",
                    is_default=True,
                    supports_reasoning=True,
                ),
            )
        )


@pytest.mark.asyncio
async def test_model_catalog_returns_selection_metadata_only() -> None:
    app = create_app(runtime_factory=runtime_factory())
    app.dependency_overrides[get_model_catalog] = StubCatalog
    client = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    )

    async with app.router.lifespan_context(app), client:
        response = await client.get("/api/v1/models")

    assert response.status_code == 200
    assert response.json() == {
        "models": [
            {
                "provider": "deepseek",
                "model": "deepseek/deepseek-v4-pro",
                "display_name": "deepseek-v4-pro",
                "is_default": True,
                "supports_reasoning": True,
            }
        ]
    }
    assert "pricing" not in response.text


def test_openapi_contains_model_catalog() -> None:
    paths = create_app(runtime_factory=runtime_factory()).openapi()["paths"]

    assert "/api/v1/models" in paths
