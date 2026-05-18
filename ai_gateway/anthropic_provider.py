"""Anthropic Messages API provider adapter for the AI gateway."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from ai_gateway.errors import GatewayToolArgumentError, StructuredOutputValidationError
from ai_gateway.models import (
    AiGateway,
    AiGatewayConfig,
    AiMessage,
    AiRequest,
    AiResponse,
    AiUsage,
    ChatMessage,
    ToolCall,
    ToolResultMessage,
    ToolSpec,
)


class AnthropicProvider(AiGateway):
    """Provider adapter backed by Anthropic's Messages API."""

    def __init__(self, config: AiGatewayConfig | None = None, client: Any | None = None) -> None:
        self.config = config or AiGatewayConfig(provider="anthropic")
        self.client = client or self._create_client()
        self._tool_use_cache: dict[str, dict[str, Any]] = {}

    def _create_client(self) -> Any:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise RuntimeError("The anthropic package is required to use AnthropicProvider.") from exc

        kwargs: dict[str, Any] = {}
        if self.config.api_key:
            kwargs["api_key"] = self.config.api_key
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        if self.config.timeout is not None:
            kwargs["timeout"] = self.config.timeout
        return AsyncAnthropic(**kwargs)

    async def get_response(self, request: AiRequest) -> AiResponse:
        messages, system = self._serialize_messages(request.messages, request.provider_context)
        kwargs: dict[str, Any] = {
            "model": request.model or self.config.model,
            "max_tokens": 4096,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if request.tools:
            kwargs["tools"] = [self._serialize_tool(tool) for tool in request.tools]
        if request.structured_output_schema is not None:
            kwargs["output_config"] = {
                "format": self._serialize_structured_output(request.structured_output_schema)
            }
        kwargs.update(request.options)

        response = await self.client.messages.create(**kwargs)
        normalized = self._normalize_response(response, request.structured_output_schema, request.mode)
        self._cache_tool_use_blocks(normalized.tool_calls)
        return normalized

    def _serialize_messages(
        self,
        messages: list[AiMessage],
        provider_context: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], str | list[dict[str, Any]] | None]:
        serialized: list[dict[str, Any]] = []
        system_parts: list[str] = []
        system_blocks: list[dict[str, Any]] = []
        pending_tool_results: list[ToolResultMessage] = []

        def flush_tool_results() -> None:
            nonlocal pending_tool_results
            if not pending_tool_results:
                return
            if not self._last_message_has_tool_use(serialized):
                tool_use_blocks = self._tool_use_blocks_for_results(pending_tool_results, provider_context)
                if tool_use_blocks:
                    serialized.append({"role": "assistant", "content": tool_use_blocks})
            serialized.append(
                {
                    "role": "user",
                    "content": [self._serialize_tool_result(message) for message in pending_tool_results],
                }
            )
            pending_tool_results = []

        for message in messages:
            if isinstance(message, ToolResultMessage):
                pending_tool_results.append(message)
                continue
            flush_tool_results()
            if message.role == "system":
                if isinstance(message.content, str):
                    system_parts.append(message.content)
                else:
                    system_blocks.extend(message.content)
                continue
            serialized.append({"role": message.role, "content": message.content})

        flush_tool_results()

        system: str | list[dict[str, Any]] | None = None
        if system_blocks:
            if system_parts:
                system_blocks.insert(0, {"type": "text", "text": "\n\n".join(system_parts)})
            system = system_blocks
        elif system_parts:
            system = "\n\n".join(system_parts)
        return serialized, system

    def _serialize_tool_result(self, message: ToolResultMessage) -> dict[str, Any]:
        return {
            "type": "tool_result",
            "tool_use_id": message.tool_call_id,
            "content": message.content,
        }

    def _last_message_has_tool_use(self, messages: list[dict[str, Any]]) -> bool:
        if not messages or messages[-1].get("role") != "assistant":
            return False
        content = messages[-1].get("content")
        if not isinstance(content, list):
            return False
        return any(self._read_attr(block, "type") == "tool_use" for block in content)

    def _tool_use_blocks_for_results(
        self,
        results: list[ToolResultMessage],
        provider_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        context_blocks = provider_context.get("anthropic_tool_use_blocks", [])
        block_by_id = {self._read_attr(block, "id"): self._to_content_block(block) for block in context_blocks}
        blocks: list[dict[str, Any]] = []
        for result in results:
            block = block_by_id.get(result.tool_call_id) or self._tool_use_cache.get(result.tool_call_id)
            if block:
                blocks.append(block)
        return blocks

    def _serialize_tool(self, tool: ToolSpec) -> dict[str, Any]:
        serialized: dict[str, Any] = {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.parameters,
        }
        if tool.strict is not None:
            serialized["strict"] = tool.strict
        return serialized

    def _serialize_structured_output(self, schema: type[BaseModel]) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "schema": schema.model_json_schema(),
        }

    def _normalize_response(
        self,
        response: Any,
        structured_output_schema: type[BaseModel] | None,
        mode: str | None,
    ) -> AiResponse:
        text = self._extract_text(response)
        structured_output = self._extract_structured_output(response, text, structured_output_schema)
        tool_calls = self._extract_tool_calls(response)
        return AiResponse(
            text=text,
            structured_output=structured_output,
            tool_calls=tool_calls,
            finish_reason=self._read_attr(response, "stop_reason"),
            usage=self._extract_usage(response),
            mode=mode,
            provider_metadata={
                "provider": "anthropic",
                "response_id": self._read_attr(response, "id"),
                "model": self._read_attr(response, "model"),
                "tool_use_blocks": [self._to_content_block(call.raw) for call in tool_calls],
            },
        )

    def _extract_text(self, response: Any) -> str | None:
        chunks: list[str] = []
        for block in self._read_attr(response, "content", []) or []:
            if self._read_attr(block, "type") == "text":
                text = self._read_attr(block, "text")
                if text:
                    chunks.append(text)
        return "\n".join(chunks) if chunks else None

    def _extract_structured_output(
        self,
        response: Any,
        text: str | None,
        schema: type[BaseModel] | None,
    ) -> BaseModel | None:
        if schema is None:
            return None
        parsed = self._read_attr(response, "parsed")
        if parsed is not None:
            try:
                return parsed if isinstance(parsed, schema) else schema.model_validate(parsed)
            except ValidationError as exc:
                raise StructuredOutputValidationError(str(exc)) from exc
        if not text:
            return None
        try:
            return schema.model_validate_json(text)
        except (ValueError, ValidationError) as exc:
            raise StructuredOutputValidationError(str(exc)) from exc

    def _extract_tool_calls(self, response: Any) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for block in self._read_attr(response, "content", []) or []:
            if self._read_attr(block, "type") != "tool_use":
                continue
            raw_input = self._read_attr(block, "input", {})
            if raw_input in (None, ""):
                arguments = {}
            elif isinstance(raw_input, dict):
                arguments = raw_input
            else:
                raise GatewayToolArgumentError(f"Tool input must be JSON object data: {block!r}")
            calls.append(
                ToolCall(
                    id=self._read_attr(block, "id"),
                    name=self._read_attr(block, "name"),
                    arguments=arguments,
                    raw=block,
                )
            )
        return calls

    def _extract_usage(self, response: Any) -> AiUsage | None:
        usage = self._read_attr(response, "usage")
        if usage is None:
            return None
        input_tokens = self._read_attr(usage, "input_tokens")
        output_tokens = self._read_attr(usage, "output_tokens")
        total_tokens = self._read_attr(usage, "total_tokens")
        if total_tokens is None and input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens
        return AiUsage(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=total_tokens)

    def _cache_tool_use_blocks(self, calls: list[ToolCall]) -> None:
        for call in calls:
            self._tool_use_cache[call.id] = self._to_content_block(call.raw)

    def _to_content_block(self, block: Any) -> dict[str, Any]:
        if isinstance(block, dict):
            return block
        return {
            "type": self._read_attr(block, "type"),
            "id": self._read_attr(block, "id"),
            "name": self._read_attr(block, "name"),
            "input": self._read_attr(block, "input"),
        }

    def _read_attr(self, value: Any, name: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

