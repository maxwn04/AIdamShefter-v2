# AI Gateway

`ai_gateway` is a lightweight model I/O layer for chat-style AI calls. It is independent from `reporter/` and `datalayer/`: callers provide messages, optional tool definitions, and optional structured output schemas, then receive normalized text, structured output, and tool-call requests.

The gateway does not execute tools. Application code owns the loop that runs datalayer or app tools and sends tool results back to the model.

## Goals

- Provide one stable interface for model calls.
- Keep provider-specific SDK shapes out of application code.
- Support assistant text, structured output, and tool calls.
- Reuse existing OpenAI function-calling tool JSON schemas through `ToolSpec`.
- Avoid orchestration dependencies such as LangChain, LiteLLM, or the OpenAI Agents SDK inside this package.

## Public Interface

```python
from ai_gateway import (
    AiGateway,
    AiGatewayConfig,
    AiRequest,
    AiResponse,
    ChatMessage,
    ToolSpec,
    ToolCall,
    ToolResultMessage,
    OpenAIGateway,
    create_gateway,
)
```

### Core Types

- `ChatMessage`: A normal `system`, `user`, or `assistant` message.
- `ToolSpec`: A provider-neutral function definition with `name`, `description`, and JSON Schema `parameters`.
- `ToolCall`: A model-requested tool call with parsed JSON `arguments`.
- `ToolResultMessage`: A tool result tied to a previous `tool_call_id`.
- `AiRequest`: Messages plus optional tools, model options, mode metadata, and structured output schema.
- `AiResponse`: Normalized assistant text, structured output, tool calls, finish reason, usage, and provider metadata.
- `AiGatewayConfig`: Provider, API key, model, base URL, and timeout.
- `AiGateway`: Abstract interface implemented by concrete providers.

## Architecture

```text
Application
  |
  | AiRequest(messages, tools, schema, options)
  v
ai_gateway
  |
  | provider-specific SDK request
  v
Model Provider
  |
  | provider-specific response
  v
ai_gateway
  |
  | AiResponse(text, structured_output, tool_calls)
  v
Application
```

The application is responsible for any higher-level workflow:

1. Build messages and tool specs.
2. Call `gateway.get_response(...)`.
3. If the response contains tool calls, execute those calls with app-owned handlers.
4. Append `ToolResultMessage` entries.
5. Call the gateway again.

This keeps orchestration, mode switching, authorization, and datalayer access outside the gateway.

## Basic Usage

```python
from ai_gateway import AiRequest, ChatMessage, create_gateway

gateway = create_gateway()

response = await gateway.get_response(
    AiRequest(
        messages=[
            ChatMessage(role="system", content="You are a fantasy football analyst."),
            ChatMessage(role="user", content="Summarize week 8."),
        ],
        model="gpt-5-mini",
    )
)

print(response.text)
```

## Tool Calling

Tools are passed in as `ToolSpec` objects. Existing OpenAI-style tool JSON can be adapted directly:

```python
from ai_gateway import AiRequest, ChatMessage, ToolResultMessage, ToolSpec
from datalayer.tools import SLEEPER_TOOLS, create_tool_handlers

tools = ToolSpec.from_openai_tools(SLEEPER_TOOLS)
handlers = create_tool_handlers(data)

messages = [
    ChatMessage(role="user", content="Who had the best week 8 performance?")
]

response = await gateway.get_response(AiRequest(messages=messages, tools=tools))

for call in response.tool_calls:
    result = handlers[call.name](**call.arguments)
    messages.append(ToolResultMessage.from_call(call, result))

final_response = await gateway.get_response(AiRequest(messages=messages, tools=tools))
print(final_response.text)
```

`ToolResultMessage.from_call(...)` serializes non-string results as JSON. Tool execution errors should be handled by the application, which can choose whether to raise, retry, or send an error result back to the model.

## Structured Output

Pass a Pydantic model class as `structured_output_schema`. The OpenAI adapter sends it as a JSON Schema response format and validates the returned text into that model.

```python
from pydantic import BaseModel

from ai_gateway import AiRequest, ChatMessage


class Storyline(BaseModel):
    headline: str
    summary: str


response = await gateway.get_response(
    AiRequest(
        messages=[ChatMessage(role="user", content="Find the lead storyline.")],
        structured_output_schema=Storyline,
    )
)

storyline = response.structured_output
```

Invalid structured output raises `StructuredOutputValidationError`.

## OpenAI Provider

`OpenAIGateway` uses the official OpenAI Python SDK and the Responses API.

Configuration defaults:

- `provider="openai"`
- `api_key` from `OPENAI_API_KEY`
- `model` from `REPORTER_MODEL`, falling back to `gpt-5-mini`

```python
from ai_gateway import AiGatewayConfig, create_gateway

gateway = create_gateway(
    AiGatewayConfig(
        provider="openai",
        model="gpt-5-mini",
        timeout=30,
    )
)
```

Provider-specific request options can be passed through `AiRequest.options`:

```python
response = await gateway.get_response(
    AiRequest(
        messages=messages,
        options={"temperature": 0.2, "max_output_tokens": 1000},
    )
)
```

`provider_context` supports provider metadata needed across calls, such as `previous_response_id` for OpenAI Responses API continuation.

## Errors

- `UnsupportedProviderError`: Raised by `create_gateway` for unknown providers.
- `GatewayToolArgumentError`: Raised when a provider returns malformed tool-call arguments.
- `StructuredOutputValidationError`: Raised when structured output cannot be validated into the requested Pydantic model.

## Tests

```bash
pytest ai_gateway/tests/
pytest ai_gateway/tests reporter/tests
pytest
```

The gateway tests use a fake OpenAI client, so they do not require network access or an API key.
