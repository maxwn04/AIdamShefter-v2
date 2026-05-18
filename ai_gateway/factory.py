"""Gateway factory."""

from __future__ import annotations

from typing import Any

from ai_gateway.anthropic_provider import AnthropicProvider
from ai_gateway.errors import UnsupportedProviderError
from ai_gateway.model_registry import normalize_provider
from ai_gateway.models import AiGateway, AiGatewayConfig
from ai_gateway.openai_provider import OpenAIProvider
from ai_gateway.routing_gateway import ModelRoutingGateway


def create_gateway(config: AiGatewayConfig | None = None, client: Any | None = None) -> AiGateway:
    """Create a gateway implementation for the configured provider."""
    gateway_config = config or AiGatewayConfig()
    provider = normalize_provider(gateway_config.provider)
    if provider == "auto":
        return ModelRoutingGateway(gateway_config)
    if provider == "openai":
        if client is None:
            return ModelRoutingGateway(gateway_config)
        return OpenAIProvider(gateway_config, client=client)
    if provider == "anthropic":
        if client is None:
            return ModelRoutingGateway(gateway_config)
        return AnthropicProvider(gateway_config, client=client)
    raise UnsupportedProviderError(f"Unsupported AI provider: {gateway_config.provider}")
