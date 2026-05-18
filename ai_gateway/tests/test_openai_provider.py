"""Tests for the OpenAI provider adapter."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel

from ai_gateway import (
    AiGatewayConfig,
    AiRequest,
    ChatMessage,
    GatewayToolArgumentError,
    OpenAIProvider,
    StructuredOutputValidationError,
    ToolCall,
    ToolResultMessage,
    ToolSpec,
)


class FakeResponses:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self.response


class FakeClient:
    def __init__(self, response: Any) -> None:
        self.responses = FakeResponses(response)


class ArticleShape(BaseModel):
    title: str
    score: int


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_plain_text_response_normalizes():
    client = FakeClient(
        {
            "id": "resp_123",
            "model": "gpt-test",
            "status": "completed",
            "output_text": "Week recap",
            "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
        }
    )
    gateway = OpenAIProvider(AiGatewayConfig(model="gpt-test"), client=client)

    response = run(gateway.get_response(AiRequest(messages=[ChatMessage(role="user", content="recap")])))

    assert response.text == "Week recap"
    assert response.finish_reason == "completed"
    assert response.usage is not None
    assert response.usage.input_tokens == 10
    assert response.provider_metadata["response_id"] == "resp_123"
    assert client.responses.kwargs is not None
    assert client.responses.kwargs["input"] == [{"role": "user", "content": "recap"}]


def test_maps_tools_into_responses_request():
    client = FakeClient({"status": "completed", "output_text": "ok"})
    gateway = OpenAIProvider(AiGatewayConfig(model="gpt-test"), client=client)

    run(
        gateway.get_response(
            AiRequest(
                messages=[ChatMessage(role="user", content="look up standings")],
                tools=[
                    ToolSpec(
                        name="standings",
                        description="Get standings",
                        parameters={"type": "object", "properties": {"week": {"type": "integer"}}},
                    )
                ],
                options={"temperature": 0.2},
            )
        )
    )

    assert client.responses.kwargs is not None
    assert client.responses.kwargs["model"] == "gpt-test"
    assert client.responses.kwargs["temperature"] == 0.2
    assert client.responses.kwargs["tools"] == [
        {
            "type": "function",
            "name": "standings",
            "description": "Get standings",
            "parameters": {"type": "object", "properties": {"week": {"type": "integer"}}},
            "strict": None,
        }
    ]


def test_tool_call_response_normalizes_arguments():
    client = FakeClient(
        {
            "status": "requires_action",
            "output": [
                {
                    "type": "function_call",
                    "call_id": "call_abc",
                    "name": "team_game",
                    "arguments": '{"roster_key": "Schefter", "week": 8}',
                }
            ],
        }
    )
    gateway = OpenAIProvider(AiGatewayConfig(model="gpt-test"), client=client)

    response = run(gateway.get_response(AiRequest(messages=[ChatMessage(role="user", content="team game")])))

    assert response.tool_calls == [
        ToolCall(id="call_abc", name="team_game", arguments={"roster_key": "Schefter", "week": 8}, raw=response.tool_calls[0].raw)
    ]


def test_malformed_tool_arguments_raise_gateway_error():
    client = FakeClient(
        {
            "output": [
                {
                    "type": "function_call",
                    "call_id": "call_abc",
                    "name": "team_game",
                    "arguments": "{broken",
                }
            ],
        }
    )
    gateway = OpenAIProvider(AiGatewayConfig(model="gpt-test"), client=client)

    with pytest.raises(GatewayToolArgumentError):
        run(gateway.get_response(AiRequest(messages=[ChatMessage(role="user", content="team game")])))


def test_tool_result_message_serializes_for_next_request():
    client = FakeClient({"status": "completed", "output_text": "thanks"})
    gateway = OpenAIProvider(AiGatewayConfig(model="gpt-test"), client=client)

    run(
        gateway.get_response(
            AiRequest(
                messages=[
                    ChatMessage(role="user", content="recap"),
                    ToolResultMessage(tool_call_id="call_abc", name="standings", content='{"rank": 1}'),
                ],
                provider_context={"previous_response_id": "resp_prev"},
            )
        )
    )

    assert client.responses.kwargs is not None
    assert client.responses.kwargs["previous_response_id"] == "resp_prev"
    assert client.responses.kwargs["input"][1] == {
        "type": "function_call_output",
        "call_id": "call_abc",
        "output": '{"rank": 1}',
    }


def test_structured_output_schema_is_sent_and_validated():
    client = FakeClient({"status": "completed", "output_text": '{"title": "Recap", "score": 98}'})
    gateway = OpenAIProvider(AiGatewayConfig(model="gpt-test"), client=client)

    response = run(
        gateway.get_response(
            AiRequest(
                messages=[ChatMessage(role="user", content="json")],
                structured_output_schema=ArticleShape,
            )
        )
    )

    assert client.responses.kwargs is not None
    assert client.responses.kwargs["text"]["format"]["name"] == "ArticleShape"
    assert response.structured_output == ArticleShape(title="Recap", score=98)


def test_invalid_structured_output_raises_gateway_error():
    client = FakeClient({"status": "completed", "output_text": '{"title": "Recap"}'})
    gateway = OpenAIProvider(AiGatewayConfig(model="gpt-test"), client=client)

    with pytest.raises(StructuredOutputValidationError):
        run(
            gateway.get_response(
                AiRequest(
                    messages=[ChatMessage(role="user", content="json")],
                    structured_output_schema=ArticleShape,
                )
            )
        )
