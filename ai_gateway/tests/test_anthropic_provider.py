"""Tests for the Anthropic provider adapter."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel

from ai_gateway import (
    AiGatewayConfig,
    AiRequest,
    AnthropicProvider,
    ChatMessage,
    GatewayToolArgumentError,
    StructuredOutputValidationError,
    ToolCall,
    ToolResultMessage,
    ToolSpec,
)


class FakeMessages:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self.response


class FakeClient:
    def __init__(self, response: Any) -> None:
        self.messages = FakeMessages(response)


class ArticleShape(BaseModel):
    title: str
    score: int


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_plain_text_response_normalizes_and_system_message_serializes():
    client = FakeClient(
        {
            "id": "msg_123",
            "model": "claude-test",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": "Week recap"}],
            "usage": {"input_tokens": 10, "output_tokens": 4},
        }
    )
    gateway = AnthropicProvider(AiGatewayConfig(provider="anthropic", model="claude-test"), client=client)

    response = run(
        gateway.get_response(
            AiRequest(
                messages=[
                    ChatMessage(role="system", content="You are a fantasy analyst."),
                    ChatMessage(role="user", content="recap"),
                ]
            )
        )
    )

    assert response.text == "Week recap"
    assert response.finish_reason == "end_turn"
    assert response.usage is not None
    assert response.usage.total_tokens == 14
    assert response.provider_metadata["provider"] == "anthropic"
    assert client.messages.kwargs is not None
    assert client.messages.kwargs["system"] == "You are a fantasy analyst."
    assert client.messages.kwargs["messages"] == [{"role": "user", "content": "recap"}]


def test_maps_tools_into_anthropic_request():
    client = FakeClient({"stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]})
    gateway = AnthropicProvider(AiGatewayConfig(provider="anthropic", model="claude-test"), client=client)

    run(
        gateway.get_response(
            AiRequest(
                messages=[ChatMessage(role="user", content="look up standings")],
                tools=[
                    ToolSpec(
                        name="standings",
                        description="Get standings",
                        parameters={"type": "object", "properties": {"week": {"type": "integer"}}},
                        strict=True,
                    )
                ],
                options={"temperature": 0.2},
            )
        )
    )

    assert client.messages.kwargs is not None
    assert client.messages.kwargs["model"] == "claude-test"
    assert client.messages.kwargs["temperature"] == 0.2
    assert client.messages.kwargs["tools"] == [
        {
            "name": "standings",
            "description": "Get standings",
            "input_schema": {"type": "object", "properties": {"week": {"type": "integer"}}},
            "strict": True,
        }
    ]


def test_tool_call_response_normalizes_arguments():
    client = FakeClient(
        {
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "team_game",
                    "input": {"roster_key": "Schefter", "week": 8},
                }
            ],
        }
    )
    gateway = AnthropicProvider(AiGatewayConfig(provider="anthropic", model="claude-test"), client=client)

    response = run(gateway.get_response(AiRequest(messages=[ChatMessage(role="user", content="team game")])))

    assert response.tool_calls == [
        ToolCall(id="toolu_123", name="team_game", arguments={"roster_key": "Schefter", "week": 8}, raw=response.tool_calls[0].raw)
    ]
    assert response.provider_metadata["tool_use_blocks"] == [
        {
            "type": "tool_use",
            "id": "toolu_123",
            "name": "team_game",
            "input": {"roster_key": "Schefter", "week": 8},
        }
    ]


def test_malformed_tool_arguments_raise_gateway_error():
    client = FakeClient(
        {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "team_game",
                    "input": "broken",
                }
            ],
        }
    )
    gateway = AnthropicProvider(AiGatewayConfig(provider="anthropic", model="claude-test"), client=client)

    with pytest.raises(GatewayToolArgumentError):
        run(gateway.get_response(AiRequest(messages=[ChatMessage(role="user", content="team game")])))


def test_tool_result_message_serializes_for_next_request():
    client = FakeClient({"stop_reason": "end_turn", "content": [{"type": "text", "text": "thanks"}]})
    gateway = AnthropicProvider(AiGatewayConfig(provider="anthropic", model="claude-test"), client=client)
    gateway._tool_use_cache["toolu_123"] = {
        "type": "tool_use",
        "id": "toolu_123",
        "name": "standings",
        "input": {"week": 8},
    }

    run(
        gateway.get_response(
            AiRequest(
                messages=[
                    ChatMessage(role="user", content="recap"),
                    ToolResultMessage(tool_call_id="toolu_123", name="standings", content='{"rank": 1}'),
                ]
            )
        )
    )

    assert client.messages.kwargs is not None
    assert client.messages.kwargs["messages"][1] == {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_123",
                "name": "standings",
                "input": {"week": 8},
            }
        ],
    }
    assert client.messages.kwargs["messages"][2] == {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "toolu_123", "content": '{"rank": 1}'}],
    }


def test_structured_output_schema_is_sent_and_validated():
    client = FakeClient({"stop_reason": "end_turn", "content": [{"type": "text", "text": '{"title": "Recap", "score": 98}'}]})
    gateway = AnthropicProvider(AiGatewayConfig(provider="anthropic", model="claude-test"), client=client)

    response = run(
        gateway.get_response(
            AiRequest(
                messages=[ChatMessage(role="user", content="json")],
                structured_output_schema=ArticleShape,
            )
        )
    )

    assert client.messages.kwargs is not None
    assert client.messages.kwargs["output_config"]["format"]["type"] == "json_schema"
    assert response.structured_output == ArticleShape(title="Recap", score=98)


def test_invalid_structured_output_raises_gateway_error():
    client = FakeClient({"stop_reason": "end_turn", "content": [{"type": "text", "text": '{"title": "Recap"}'}]})
    gateway = AnthropicProvider(AiGatewayConfig(provider="anthropic", model="claude-test"), client=client)

    with pytest.raises(StructuredOutputValidationError):
        run(
            gateway.get_response(
                AiRequest(
                    messages=[ChatMessage(role="user", content="json")],
                    structured_output_schema=ArticleShape,
                )
            )
        )
