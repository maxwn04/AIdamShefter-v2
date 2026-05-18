"""Hard-coded AI gateway model registry."""

from __future__ import annotations

import os
from dataclasses import dataclass

from ai_gateway.errors import UnsupportedProviderError

ProviderName = str

OPENAI_PROVIDER = "openai"
ANTHROPIC_PROVIDER = "anthropic"
AUTO_PROVIDER = "auto"

PROVIDER_ALIASES: dict[str, ProviderName] = {
    "auto": AUTO_PROVIDER,
    "openai": OPENAI_PROVIDER,
    "gpt": OPENAI_PROVIDER,
    "chatgpt": OPENAI_PROVIDER,
    "anthropic": ANTHROPIC_PROVIDER,
    "claude": ANTHROPIC_PROVIDER,
}

DEFAULT_PROVIDER_ORDER: tuple[ProviderName, ...] = (OPENAI_PROVIDER, ANTHROPIC_PROVIDER)


@dataclass(frozen=True)
class ModelSpec:
    """A known model and the provider that serves it."""

    name: str
    provider: ProviderName


MODEL_REGISTRY: dict[str, ModelSpec] = {
    "gpt-5.2": ModelSpec("gpt-5.2", OPENAI_PROVIDER),
    "gpt-5.2-pro": ModelSpec("gpt-5.2-pro", OPENAI_PROVIDER),
    "gpt-5.1": ModelSpec("gpt-5.1", OPENAI_PROVIDER),
    "gpt-5": ModelSpec("gpt-5", OPENAI_PROVIDER),
    "gpt-5-pro": ModelSpec("gpt-5-pro", OPENAI_PROVIDER),
    "gpt-5-mini": ModelSpec("gpt-5-mini", OPENAI_PROVIDER),
    "gpt-5o": ModelSpec("gpt-5o", OPENAI_PROVIDER),
    "gpt-4.1": ModelSpec("gpt-4.1", OPENAI_PROVIDER),
    "gpt-4.1-mini": ModelSpec("gpt-4.1-mini", OPENAI_PROVIDER),
    "claude-opus-4-7": ModelSpec("claude-opus-4-7", ANTHROPIC_PROVIDER),
    "claude-opus-4-6": ModelSpec("claude-opus-4-6", ANTHROPIC_PROVIDER),
    "claude-opus-4-5-20251101": ModelSpec("claude-opus-4-5-20251101", ANTHROPIC_PROVIDER),
    "claude-opus-4-1-20250805": ModelSpec("claude-opus-4-1-20250805", ANTHROPIC_PROVIDER),
    "claude-sonnet-4-6": ModelSpec("claude-sonnet-4-6", ANTHROPIC_PROVIDER),
    "claude-sonnet-4-5-20250929": ModelSpec("claude-sonnet-4-5-20250929", ANTHROPIC_PROVIDER),
    "claude-haiku-4-5-20251001": ModelSpec("claude-haiku-4-5-20251001", ANTHROPIC_PROVIDER),
}

MODEL_ALIASES: dict[str, str] = {
    "openai": "gpt-5o",
    "gpt": "gpt-5o",
    "gpt-default": "gpt-5o",
    "claude": "claude-sonnet-4-6",
    "anthropic": "claude-sonnet-4-6",
    "claude-sonnet": "claude-sonnet-4-6",
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-sonnet-4-5": "claude-sonnet-4-5-20250929",
    "claude-haiku": "claude-haiku-4-5-20251001",
    "claude-haiku-4-5": "claude-haiku-4-5-20251001",
    "claude-opus": "claude-opus-4-7",
    "claude-opus-4-7": "claude-opus-4-7",
    "claude-opus-4-6": "claude-opus-4-6",
    "claude-opus-4-5": "claude-opus-4-5-20251101",
    "claude-opus-4.1": "claude-opus-4-1-20250805",
    "claude-opus-4-1": "claude-opus-4-1-20250805",
}


def normalize_provider(provider: str | None) -> ProviderName:
    """Normalize provider aliases used by CLI/config callers."""
    if not provider:
        return AUTO_PROVIDER
    normalized = PROVIDER_ALIASES.get(provider.lower())
    if normalized is None:
        raise UnsupportedProviderError(f"Unsupported AI provider: {provider}")
    return normalized


def normalize_model_name(model: str | None) -> str | None:
    """Resolve model aliases without guessing provider from prefixes."""
    if not model:
        return None
    model_name = model.lower()
    if model_name in MODEL_ALIASES:
        return MODEL_ALIASES[model_name]
    if model_name in MODEL_REGISTRY:
        return model_name
    return model


def provider_for_model(model: str | None) -> ProviderName | None:
    """Return the registered provider for a known model."""
    normalized = normalize_model_name(model)
    if not normalized:
        return None
    spec = MODEL_REGISTRY.get(normalized)
    return spec.provider if spec else None


def default_model_for_provider(provider: ProviderName) -> str:
    """Return the configured default model for a provider."""
    normalized = normalize_provider(provider)
    if normalized == ANTHROPIC_PROVIDER:
        return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    if normalized == OPENAI_PROVIDER:
        return os.getenv("OPENAI_MODEL") or os.getenv("REPORTER_MODEL", "gpt-5o")
    raise UnsupportedProviderError(f"Unsupported AI provider: {provider}")


def api_key_for_provider(provider: ProviderName) -> str | None:
    """Return the API key env var for a provider."""
    normalized = normalize_provider(provider)
    if normalized == ANTHROPIC_PROVIDER:
        return os.getenv("ANTHROPIC_API_KEY")
    if normalized == OPENAI_PROVIDER:
        return os.getenv("OPENAI_API_KEY")
    return None


def available_providers() -> list[ProviderName]:
    """List providers configured with API keys in fallback order."""
    return [provider for provider in DEFAULT_PROVIDER_ORDER if api_key_for_provider(provider)]
