"""Provider-neutral request and response models for AI chat calls."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_gateway.model_registry import default_model_for_provider, normalize_provider


class ChatMessage(BaseModel):
    """A normal conversation message."""

    role: Literal["system", "user", "assistant"]
    content: str | list[dict[str, Any]]


class ToolSpec(BaseModel):
    """Provider-neutral function/tool definition."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    strict: bool | None = None

    @classmethod
    def from_openai_tool(cls, tool: dict[str, Any]) -> "ToolSpec":
        """Create a tool spec from OpenAI function-calling JSON."""
        function = tool.get("function", tool)
        return cls(
            name=function["name"],
            description=function.get("description", ""),
            parameters=function.get("parameters", {"type": "object", "properties": {}}),
            strict=function.get("strict"),
        )

    @classmethod
    def from_openai_tools(cls, tools: list[dict[str, Any]]) -> list["ToolSpec"]:
        """Create tool specs from OpenAI function-calling JSON tools."""
        return [cls.from_openai_tool(tool) for tool in tools]


class ToolCall(BaseModel):
    """A model-requested tool call with parsed JSON arguments."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    raw: Any = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ToolResultMessage(BaseModel):
    """A tool execution result tied to a previous tool call."""

    role: Literal["tool"] = "tool"
    tool_call_id: str
    content: str
    name: str | None = None

    @classmethod
    def from_call(cls, call: ToolCall, result: Any) -> "ToolResultMessage":
        """Create a tool result message from a tool call and arbitrary result."""
        if isinstance(result, str):
            content = result
        else:
            content = json.dumps(result, default=str)
        return cls(tool_call_id=call.id, name=call.name, content=content)


AiMessage = ChatMessage | ToolResultMessage


class AiUsage(BaseModel):
    """Token usage normalized across providers."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class AiGatewayConfig(BaseModel):
    """Configuration for a gateway provider."""

    provider: str = Field(default_factory=lambda: os.getenv("AI_GATEWAY_PROVIDER", "auto"))
    api_key: str | None = None
    model: str | None = Field(default_factory=lambda: os.getenv("AI_GATEWAY_MODEL"))
    base_url: str | None = None
    timeout: float | None = None

    def model_post_init(self, __context: Any) -> None:
        provider = normalize_provider(self.provider)
        if self.api_key is None:
            if provider == "anthropic":
                self.api_key = os.getenv("ANTHROPIC_API_KEY")
            elif provider == "openai":
                self.api_key = os.getenv("OPENAI_API_KEY")
        if self.model is None:
            if provider in {"anthropic", "openai"}:
                self.model = default_model_for_provider(provider)


class AiRequest(BaseModel):
    """Provider-neutral model request."""

    messages: list[AiMessage]
    tools: list[ToolSpec] = Field(default_factory=list)
    model: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    structured_output_schema: type[BaseModel] | None = Field(default=None, exclude=True)
    mode: str | None = None
    provider_context: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class AiResponse(BaseModel):
    """Provider-neutral model response."""

    text: str | None = None
    structured_output: BaseModel | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str | None = None
    usage: AiUsage | None = None
    mode: str | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class AiGateway(ABC):
    """Abstract gateway interface."""

    @abstractmethod
    async def get_response(self, request: AiRequest) -> AiResponse:
        """Send a request to a model provider and return normalized output."""
