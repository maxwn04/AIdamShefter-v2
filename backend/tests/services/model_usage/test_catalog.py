from decimal import Decimal

from backend.config import ModelCatalogSettings
from backend.resources.reporting.ai_calls import TokenUsage
from backend.services.model_usage import LiteLLMModelRegistry, ModelCatalogService


MODEL_MAP = {
    "deepseek/deepseek-v4-pro": {
        "litellm_provider": "deepseek",
        "supports_reasoning": True,
        "input_cost_per_token": 0.000001,
        "cache_read_input_token_cost": 0.0000005,
        "output_cost_per_token": 0.000002,
        "output_cost_per_reasoning_token": 0.000003,
    }
}


def test_settings_build_ordered_deduplicated_model_chain(monkeypatch) -> None:
    monkeypatch.setenv("REPORTER_MODEL", "deepseek/deepseek-v4-pro")
    monkeypatch.setenv(
        "REPORTER_FALLBACK_MODELS",
        "gpt-5.6-luna, deepseek/deepseek-v4-pro, gpt-5.6-luna, backup",
    )

    settings = ModelCatalogSettings.from_environment()

    assert settings.model_chain() == (
        "deepseek/deepseek-v4-pro",
        "gpt-5.6-luna",
        "backup",
    )


def test_catalog_returns_selection_metadata_without_prices() -> None:
    registry = LiteLLMModelRegistry(
        remote_loader=lambda: MODEL_MAP,
        fallback_loader=lambda: {},
    )
    catalog = ModelCatalogService(
        ModelCatalogSettings(
            primary_model="deepseek/deepseek-v4-pro",
            fallback_models=("unknown-model",),
        ),
        registry,
    ).list()

    assert catalog.models[0].model_dump() == {
        "provider": "deepseek",
        "model": "deepseek/deepseek-v4-pro",
        "display_name": "deepseek-v4-pro",
        "is_default": True,
        "supports_reasoning": True,
    }
    assert catalog.models[1].model_dump() == {
        "provider": None,
        "model": "unknown-model",
        "display_name": "unknown-model",
        "is_default": False,
        "supports_reasoning": False,
    }


def test_registry_falls_back_once_and_quotes_decimal_token_cost() -> None:
    calls = {"remote": 0, "fallback": 0}

    def remote() -> dict[str, object]:
        calls["remote"] += 1
        raise OSError("offline")

    def fallback() -> dict[str, object]:
        calls["fallback"] += 1
        return MODEL_MAP

    registry = LiteLLMModelRegistry(
        remote_loader=remote,
        fallback_loader=fallback,
    )
    usage = TokenUsage(
        input_tokens=100,
        cached_input_tokens=20,
        output_tokens=50,
        reasoning_tokens=10,
    )

    assert registry.quote("deepseek", "deepseek-v4-pro", usage) == Decimal(
        "0.0002000"
    )
    assert registry.model_info("deepseek/deepseek-v4-pro") is not None
    assert calls == {"remote": 1, "fallback": 1}
    assert registry.quote(None, "unknown", usage) is None
