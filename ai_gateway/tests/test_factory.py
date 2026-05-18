"""Tests for gateway factory behavior."""

import asyncio
from typing import Any

import pytest

from ai_gateway import (
    AiGatewayConfig,
    AnthropicProvider,
    ChatMessage,
    MODEL_REGISTRY,
    ModelRoutingGateway,
    OpenAIProvider,
    UnsupportedProviderError,
    create_gateway,
)
from ai_gateway.model_registry import normalize_model_name, provider_for_model
from ai_gateway.models import AiRequest


class FakeResponses:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self.response


class FakeOpenAIClient:
    def __init__(self, response: Any) -> None:
        self.responses = FakeResponses(response)


class FakeMessages:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self.response


class FakeAnthropicClient:
    def __init__(self, response: Any) -> None:
        self.messages = FakeMessages(response)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_config_defaults_to_auto_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AI_GATEWAY_PROVIDER", raising=False)
    monkeypatch.delenv("AI_GATEWAY_MODEL", raising=False)

    config = AiGatewayConfig()

    assert config.provider == "auto"
    assert config.model is None


def test_model_registry_contains_common_provider_models():
    assert MODEL_REGISTRY["gpt-5o"].provider == "openai"
    assert MODEL_REGISTRY["gpt-5-mini"].provider == "openai"
    assert MODEL_REGISTRY["claude-opus-4-7"].provider == "anthropic"
    assert MODEL_REGISTRY["claude-opus-4-6"].provider == "anthropic"
    assert MODEL_REGISTRY["claude-sonnet-4-6"].provider == "anthropic"
    assert MODEL_REGISTRY["claude-haiku-4-5-20251001"].provider == "anthropic"
    assert normalize_model_name("Claude-Sonnet-4-6") == "claude-sonnet-4-6"
    assert normalize_model_name("GPT-5O") == "gpt-5o"


def test_unknown_model_does_not_infer_provider_from_prefix():
    assert provider_for_model("claude-test") is None
    assert provider_for_model("gpt-test") is None


def test_create_gateway_supports_openai_with_injected_client():
    client = object()

    gateway = create_gateway(AiGatewayConfig(provider="openai"), client=client)

    assert isinstance(gateway, OpenAIProvider)
    assert gateway.client is client


def test_create_gateway_supports_anthropic_with_injected_client():
    client = object()

    gateway = create_gateway(AiGatewayConfig(provider="claude"), client=client)

    assert isinstance(gateway, AnthropicProvider)
    assert gateway.client is client


def test_create_gateway_uses_router_without_injected_client():
    gateway = create_gateway(AiGatewayConfig(provider="openai"))

    assert isinstance(gateway, ModelRoutingGateway)


def test_router_uses_requested_claude_model_when_anthropic_key_exists(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    anthropic_client = FakeAnthropicClient(
        {
            "id": "msg_123",
            "model": "claude-sonnet-4-6",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": "Claude response"}],
        }
    )
    gateway = ModelRoutingGateway(
        AiGatewayConfig(provider="auto"),
        clients={"anthropic": anthropic_client},
    )

    response = run(
        gateway.get_response(
            AiRequest(messages=[ChatMessage(role="user", content="recap")], model="claude-sonnet-4-6")
        )
    )

    assert response.text == "Claude response"
    assert response.provider_metadata["provider"] == "anthropic"
    assert response.provider_metadata["routed_provider"] == "anthropic"
    assert anthropic_client.messages.kwargs is not None
    assert anthropic_client.messages.kwargs["model"] == "claude-sonnet-4-6"


def test_router_falls_back_from_claude_to_openai_default_when_anthropic_key_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("REPORTER_MODEL", raising=False)
    openai_client = FakeOpenAIClient({"status": "completed", "output_text": "OpenAI fallback"})
    gateway = ModelRoutingGateway(
        AiGatewayConfig(provider="claude"),
        clients={"openai": openai_client},
    )

    response = run(gateway.get_response(AiRequest(messages=[ChatMessage(role="user", content="recap")])))

    assert response.text == "OpenAI fallback"
    assert response.provider_metadata["provider"] == "openai"
    assert response.provider_metadata["requested_provider"] == "anthropic"
    assert response.provider_metadata["routed_provider"] == "openai"
    assert response.provider_metadata["routed_model"] == "gpt-5o"
    assert openai_client.responses.kwargs is not None
    assert openai_client.responses.kwargs["model"] == "gpt-5o"


def test_router_treats_explicit_config_api_key_as_available(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert ModelRoutingGateway(AiGatewayConfig(provider="openai", api_key="config-key"))._provider_is_available("openai")

    openai_client = FakeOpenAIClient({"status": "completed", "output_text": "Configured key"})
    gateway = ModelRoutingGateway(
        AiGatewayConfig(provider="openai", api_key="config-key", model="gpt-configured"),
        clients={"openai": openai_client},
    )

    response = run(gateway.get_response(AiRequest(messages=[ChatMessage(role="user", content="recap")])))

    assert response.text == "Configured key"
    assert response.provider_metadata["routed_provider"] == "openai"
    assert openai_client.responses.kwargs is not None
    assert openai_client.responses.kwargs["model"] == "gpt-configured"


def test_create_gateway_rejects_unknown_provider():
    with pytest.raises(UnsupportedProviderError):
        create_gateway(AiGatewayConfig(provider="unknown"), client=object())
