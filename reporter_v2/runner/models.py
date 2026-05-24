"""Minimal chat-completion models for the v2 runner."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


ToolDef = dict[str, Any]
ChatMessage = dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    """A normalized model-requested tool call."""

    id: str
    name: str
    arguments: dict[str, Any]


def tool_result_message(call: ToolCall, result: Any) -> ChatMessage:
    """Build an OpenAI-format tool result message."""
    content = result if isinstance(result, str) else json.dumps(result, default=str)
    return {
        "role": "tool",
        "tool_call_id": call.id,
        "name": call.name,
        "content": content,
    }


def assistant_tool_call_message(
    calls: list[ToolCall],
    response: Any | None = None,
) -> ChatMessage:
    """Build the assistant message that must precede tool result messages."""
    source_message = _first_message(response) if response is not None else None
    content = _read_attr(source_message, "content")
    message: ChatMessage = {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, default=str),
                },
            }
            for call in calls
        ],
    }

    reasoning_content = _read_attr(source_message, "reasoning_content")
    if reasoning_content is not None:
        # DeepSeek thinking-mode responses must be passed back verbatim on
        # subsequent turns, or the API rejects the tool result turn.
        message["reasoning_content"] = reasoning_content

    provider_specific_fields = _read_attr(source_message, "provider_specific_fields")
    if provider_specific_fields is not None:
        message["provider_specific_fields"] = provider_specific_fields

    return message


def extract_tool_calls(response: Any) -> list[ToolCall]:
    """Extract normalized tool calls from a litellm/OpenAI-style response."""
    message = _first_message(response)
    if message is None:
        return []

    raw_calls = _read_attr(message, "tool_calls", []) or []
    calls: list[ToolCall] = []
    for raw_call in raw_calls:
        function = _read_attr(raw_call, "function", {}) or {}
        calls.append(
            ToolCall(
                id=str(_read_attr(raw_call, "id", "")),
                name=str(_read_attr(function, "name", "")),
                arguments=_parse_arguments(_read_attr(function, "arguments", {})),
            )
        )
    return calls


def extract_text(response: Any) -> str | None:
    """Extract assistant text from a litellm/OpenAI-style response."""
    message = _first_message(response)
    if message is None:
        return None

    content = _read_attr(message, "content")
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text = _read_attr(item, "text")
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts) or None
    return str(content)


def _first_message(response: Any) -> Any | None:
    choices = _read_attr(response, "choices", []) or []
    if not choices:
        return None
    return _read_attr(choices[0], "message")


def _parse_arguments(arguments: Any) -> dict[str, Any]:
    if arguments in (None, ""):
        return {}
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        parsed = json.loads(arguments)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Tool call arguments must be a JSON object.")


def _read_attr(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)
