"""Tests for provider-neutral AI gateway models."""

from ai_gateway import ToolCall, ToolResultMessage, ToolSpec


def test_tool_spec_from_openai_tool():
    spec = ToolSpec.from_openai_tool(
        {
            "type": "function",
            "function": {
                "name": "league_snapshot",
                "description": "Get league data",
                "parameters": {
                    "type": "object",
                    "properties": {"week": {"type": "integer"}},
                    "required": [],
                },
            },
        }
    )

    assert spec.name == "league_snapshot"
    assert spec.description == "Get league data"
    assert spec.parameters["properties"]["week"]["type"] == "integer"


def test_tool_result_message_from_call_serializes_result():
    call = ToolCall(id="call_123", name="league_snapshot", arguments={"week": 1})

    message = ToolResultMessage.from_call(call, {"standings": []})

    assert message.role == "tool"
    assert message.tool_call_id == "call_123"
    assert message.name == "league_snapshot"
    assert message.content == '{"standings": []}'
