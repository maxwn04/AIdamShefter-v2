"""Model-aware gateway router."""

from __future__ import annotations

from typing import Any

from ai_gateway.anthropic_provider import AnthropicProvider
from ai_gateway.errors import UnsupportedProviderError
from ai_gateway.model_registry import (
    ANTHROPIC_PROVIDER,
    AUTO_PROVIDER,
    DEFAULT_PROVIDER_ORDER,
    OPENAI_PROVIDER,
    ProviderName,
    api_key_for_provider,
    default_model_for_provider,
    normalize_model_name,
    normalize_provider,
    provider_for_model,
)
from ai_gateway.models import AiGateway, AiGatewayConfig, AiRequest, AiResponse
from ai_gateway.openai_provider import OpenAIProvider


class ModelRoutingGateway(AiGateway):
    """Route each AI request to a configured provider based on model/provider hints."""

    def __init__(
        self,
        config: AiGatewayConfig | None = None,
        clients: dict[ProviderName, Any] | None = None,
    ) -> None:
        self.config = config or AiGatewayConfig()
        self.clients = clients or {}
        self._gateways: dict[ProviderName, AiGateway] = {}

    async def get_response(self, request: AiRequest) -> AiResponse:
        requested_provider, requested_model, routed_provider, routed_model = self._resolve_route(request)
        gateway = self._get_gateway(routed_provider)
        routed_request = request.model_copy(update={"model": routed_model})
        response = await gateway.get_response(routed_request)
        response.provider_metadata.update(
            {
                "requested_provider": requested_provider,
                "requested_model": requested_model,
                "routed_provider": routed_provider,
                "routed_model": routed_model,
            }
        )
        return response

    def _resolve_route(self, request: AiRequest) -> tuple[ProviderName, str | None, ProviderName, str]:
        requested_model = normalize_model_name(request.model or self.config.model)
        configured_provider = normalize_provider(self.config.provider)
        requested_provider = configured_provider

        model_provider = provider_for_model(requested_model)
        if configured_provider == AUTO_PROVIDER:
            requested_provider = model_provider or self._first_available_provider()

        if requested_provider == AUTO_PROVIDER:
            requested_provider = self._first_available_provider()

        if self._provider_is_available(requested_provider):
            return (
                requested_provider,
                requested_model,
                requested_provider,
                requested_model or default_model_for_provider(requested_provider),
            )

        fallback_provider = self._first_available_provider(excluding={requested_provider})
        fallback_model = requested_model if model_provider == fallback_provider else None
        return (
            requested_provider,
            requested_model,
            fallback_provider,
            fallback_model or default_model_for_provider(fallback_provider),
        )

    def _first_available_provider(self, excluding: set[ProviderName] | None = None) -> ProviderName:
        excluded = excluding or set()
        for provider in DEFAULT_PROVIDER_ORDER:
            if provider not in excluded and self._provider_is_available(provider):
                return provider
        raise UnsupportedProviderError(
            "No configured AI provider API keys found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY."
        )

    def _provider_is_available(self, provider: ProviderName) -> bool:
        normalized = normalize_provider(provider)
        return normalized in self.clients or self._api_key_for_provider(normalized) is not None

    def _get_gateway(self, provider: ProviderName) -> AiGateway:
        normalized = normalize_provider(provider)
        if normalized in self._gateways:
            return self._gateways[normalized]

        provider_config = AiGatewayConfig(
            provider=normalized,
            api_key=self._api_key_for_provider(normalized),
            model=default_model_for_provider(normalized),
            base_url=self.config.base_url,
            timeout=self.config.timeout,
        )
        client = self.clients.get(normalized)
        if normalized == OPENAI_PROVIDER:
            gateway: AiGateway = OpenAIProvider(provider_config, client=client)
        elif normalized == ANTHROPIC_PROVIDER:
            gateway = AnthropicProvider(provider_config, client=client)
        else:
            raise UnsupportedProviderError(f"Unsupported AI provider: {provider}")
        self._gateways[normalized] = gateway
        return gateway

    def _api_key_for_provider(self, provider: ProviderName) -> str | None:
        configured_provider = normalize_provider(self.config.provider)
        if configured_provider == provider and self.config.api_key:
            return self.config.api_key
        return api_key_for_provider(provider)
