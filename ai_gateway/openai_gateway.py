"""OpenAI Responses API adapter for the AI gateway."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from ai_gateway.errors import GatewayToolArgumentError, StructuredOutputValidationError
from ai_gateway.models import (
    AiGateway,
    AiGatewayConfig,
    AiRequest,
    AiResponse,
    AiUsage,
    ChatMessage,
    ToolCall,
    ToolResultMessage,
    ToolSpec,
)


class OpenAIGateway(AiGateway):
    """AI gateway implementation backed by OpenAI's Responses API."""

    def __init__(self, config: AiGatewayConfig | None = None, client: Any | None = None) -> None:
        self.config = config or AiGatewayConfig()
        self.client = client or self._create_client()

    def _create_client(self) -> Any:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError("The openai package is required to use OpenAIGateway.") from exc

        kwargs: dict[str, Any] = {}
        if self.config.api_key:
            kwargs["api_key"] = self.config.api_key
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        if self.config.timeout is not None:
            kwargs["timeout"] = self.config.timeout
        return AsyncOpenAI(**kwargs)

    async def get_response(self, request: AiRequest) -> AiResponse:
        kwargs: dict[str, Any] = {
            "model": request.model or self.config.model,
            "input": [self._serialize_message(message) for message in request.messages],
        }
        if request.tools:
            kwargs["tools"] = [self._serialize_tool(tool) for tool in request.tools]
        if request.structured_output_schema is not None:
            kwargs["text"] = {"format": self._serialize_structured_output(request.structured_output_schema)}
        if "previous_response_id" in request.provider_context:
            kwargs["previous_response_id"] = request.provider_context["previous_response_id"]
        kwargs.update(request.options)

        response = await self.client.responses.create(**kwargs)
        return self._normalize_response(response, request.structured_output_schema, request.mode)

    def _serialize_message(self, message: ChatMessage | ToolResultMessage) -> dict[str, Any]:
        if isinstance(message, ToolResultMessage):
            return {
                "type": "function_call_output",
                "call_id": message.tool_call_id,
                "output": message.content,
            }
        return {"role": message.role, "content": message.content}

    def _serialize_tool(self, tool: ToolSpec) -> dict[str, Any]:
        serialized: dict[str, Any] = {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "strict": tool.strict,
        }
        return serialized

    def _serialize_structured_output(self, schema: type[BaseModel]) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "name": schema.__name__,
            "schema": schema.model_json_schema(),
            "strict": True,
        }

    def _normalize_response(
        self,
        response: Any,
        structured_output_schema: type[BaseModel] | None,
        mode: str | None,
    ) -> AiResponse:
        text = self._extract_text(response)
        structured_output = self._extract_structured_output(response, text, structured_output_schema)
        return AiResponse(
            text=text,
            structured_output=structured_output,
            tool_calls=self._extract_tool_calls(response),
            finish_reason=self._extract_finish_reason(response),
            usage=self._extract_usage(response),
            mode=mode,
            provider_metadata={
                "provider": "openai",
                "response_id": self._read_attr(response, "id"),
                "model": self._read_attr(response, "model"),
            },
        )

    def _extract_text(self, response: Any) -> str | None:
        output_text = self._read_attr(response, "output_text")
        if output_text:
            return output_text

        chunks: list[str] = []
        for item in self._iter_output_items(response):
            item_type = self._read_attr(item, "type")
            if item_type != "message":
                continue
            for content in self._read_attr(item, "content", []) or []:
                content_type = self._read_attr(content, "type")
                if content_type in {"output_text", "text"}:
                    text = self._read_attr(content, "text")
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

        parsed = self._read_attr(response, "output_parsed")
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
        for item in self._iter_output_items(response):
            item_type = self._read_attr(item, "type")
            if item_type not in {"function_call", "tool_call"}:
                continue

            raw_arguments = self._read_attr(item, "arguments", "{}")
            arguments = self._parse_arguments(raw_arguments, item)
            call_id = self._read_attr(item, "call_id") or self._read_attr(item, "id")
            name = self._read_attr(item, "name")
            calls.append(ToolCall(id=call_id, name=name, arguments=arguments, raw=item))
        return calls

    def _parse_arguments(self, raw_arguments: Any, raw_item: Any) -> dict[str, Any]:
        if raw_arguments in (None, ""):
            return {}
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if not isinstance(raw_arguments, str):
            raise GatewayToolArgumentError(f"Tool arguments must be JSON object data: {raw_item!r}")

        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise GatewayToolArgumentError(f"Malformed tool arguments: {raw_arguments}") from exc
        if not isinstance(parsed, dict):
            raise GatewayToolArgumentError(f"Tool arguments must decode to an object: {raw_arguments}")
        return parsed

    def _extract_finish_reason(self, response: Any) -> str | None:
        status = self._read_attr(response, "status")
        if status:
            return status
        for item in self._iter_output_items(response):
            finish_reason = self._read_attr(item, "finish_reason")
            if finish_reason:
                return finish_reason
        return None

    def _extract_usage(self, response: Any) -> AiUsage | None:
        usage = self._read_attr(response, "usage")
        if usage is None:
            return None
        input_tokens = self._read_attr(usage, "input_tokens")
        output_tokens = self._read_attr(usage, "output_tokens")
        total_tokens = self._read_attr(usage, "total_tokens")
        if input_tokens is None:
            input_tokens = self._read_attr(usage, "prompt_tokens")
        if output_tokens is None:
            output_tokens = self._read_attr(usage, "completion_tokens")
        return AiUsage(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=total_tokens)

    def _iter_output_items(self, response: Any) -> list[Any]:
        return self._read_attr(response, "output", []) or []

    def _read_attr(self, value: Any, name: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)
