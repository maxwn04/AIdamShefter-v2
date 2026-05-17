"""Gateway factory."""

from __future__ import annotations

from typing import Any

from ai_gateway.errors import UnsupportedProviderError
from ai_gateway.models import AiGatewayConfig
from ai_gateway.openai_gateway import OpenAIGateway


def create_gateway(config: AiGatewayConfig | None = None, client: Any | None = None) -> OpenAIGateway:
    """Create a gateway implementation for the configured provider."""
    gateway_config = config or AiGatewayConfig()
    if gateway_config.provider == "openai":
        return OpenAIGateway(gateway_config, client=client)
    raise UnsupportedProviderError(f"Unsupported AI provider: {gateway_config.provider}")
