"""Tests for gateway factory behavior."""

import pytest

from ai_gateway import AiGatewayConfig, OpenAIGateway, UnsupportedProviderError, create_gateway


def test_config_defaults_to_openai_provider():
    config = AiGatewayConfig()

    assert config.provider == "openai"
    assert config.model


def test_create_gateway_supports_openai_with_injected_client():
    client = object()

    gateway = create_gateway(AiGatewayConfig(provider="openai"), client=client)

    assert isinstance(gateway, OpenAIGateway)
    assert gateway.client is client


def test_create_gateway_rejects_unknown_provider():
    with pytest.raises(UnsupportedProviderError):
        create_gateway(AiGatewayConfig(provider="unknown"), client=object())
