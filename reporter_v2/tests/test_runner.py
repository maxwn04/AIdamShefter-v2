"""Tests for the reporter v2 runner loop."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from ai_gateway import (
    AiGateway,
    AiRequest,
    AiResponse,
    ToolCall,
    ToolResultMessage,
    ToolSpec,
)
from reporter_v2.runner.runner import Runner
from reporter_v2.runner.state import RunnerConfig
from reporter_v2.runner.tools.context import ToolContext
from reporter_v2.runner.tools.registry import ToolRegistry


class FakeGateway(AiGateway):
    def __init__(self, responses: list[AiResponse]) -> None:
        self.responses = responses
        self.requests: list[AiRequest] = []

    async def get_response(self, request: AiRequest) -> AiResponse:
        self.requests.append(request)
        if not self.responses:
            return AiResponse()
        return self.responses.pop(0)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def registry_with(
    name: str,
    handler: Callable[..., Any],
    *,
    description: str = "Test tool",
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        name,
        handler,
        ToolSpec(
            name=name,
            description=description,
            parameters={"type": "object", "properties": {}},
        ),
    )
    return registry


def tool_call(
    name: str,
    arguments: dict[str, Any] | None = None,
    call_id: str = "call_1",
) -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments or {})


def test_tool_registry_exposes_specs_and_names() -> None:
    registry = registry_with("lookup", lambda: "{}")

    assert registry.tool_names == ["lookup"]
    assert registry.tool_specs == [
        ToolSpec(
            name="lookup",
            description="Test tool",
            parameters={"type": "object", "properties": {}},
        )
    ]
    assert registry.get_handler("lookup") is not None
    assert registry.get_handler("missing") is None


def test_runner_context_tool_dispatch_updates_turn() -> None:
    seen_turns: list[int] = []

    def context_tool(ctx: ToolContext) -> str:
        seen_turns.append(ctx.turn)
        return "{}"

    registry = ToolRegistry()
    registry.register_context_tool(
        "context_tool",
        context_tool,
        ToolSpec(name="context_tool", parameters={"type": "object", "properties": {}}),
    )
    gateway = FakeGateway(
        [
            AiResponse(tool_calls=[tool_call("context_tool")]),
            AiResponse(text="Done."),
        ]
    )
    runner = Runner(gateway, registry)

    run(runner.run("system", "user"))

    assert seen_turns == [1]
    assert runner.tool_context.artifacts is runner.artifacts
    assert runner.tool_context.procedures is runner.procedures
    assert runner.tool_context.log is runner.log


def test_runner_simple_text_response() -> None:
    gateway = FakeGateway([AiResponse(text="Done.")])
    runner = Runner(gateway, ToolRegistry())

    output = run(runner.run("system", "user"))

    assert output.article == ""
    assert output.run_log_summary["total_turns"] == 1
    assert output.run_log_summary["total_tool_calls"] == 0
    assert runner.log.entries[0].event_type == "model_text"
    assert gateway.requests[0].messages[0].role == "system"
    assert gateway.requests[0].messages[1].role == "user"


def test_runner_tool_call_dispatch() -> None:
    calls: list[dict[str, Any]] = []

    def handler(*, value: int) -> dict[str, Any]:
        calls.append({"value": value})
        return {"ok": True, "value": value}

    gateway = FakeGateway(
        [
            AiResponse(tool_calls=[tool_call("lookup", {"value": 7})]),
            AiResponse(text="Done."),
        ]
    )
    runner = Runner(gateway, registry_with("lookup", handler))

    output = run(runner.run("system", "user"))

    assert calls == [{"value": 7}]
    assert output.run_log_summary["total_tool_calls"] == 1
    assert len(gateway.requests) == 2
    result_message = gateway.requests[1].messages[-1]
    assert isinstance(result_message, ToolResultMessage)
    assert result_message.tool_call_id == "call_1"
    assert result_message.content == '{"ok": true, "value": 7}'


def test_runner_submit_article_breaks_loop() -> None:
    def submit_article() -> str:
        return '{"ok": true}'

    gateway = FakeGateway(
        [
            AiResponse(tool_calls=[tool_call("submit_article")]),
            AiResponse(text="Should not be requested."),
        ]
    )
    runner = Runner(gateway, registry_with("submit_article", submit_article))

    output = run(runner.run("system", "user"))

    assert output.run_log_summary["submitted"] is True
    assert output.run_log_summary["total_turns"] == 1
    assert len(gateway.requests) == 1


def test_runner_soft_guardrail() -> None:
    gateway = FakeGateway(
        [
            AiResponse(tool_calls=[tool_call("lookup")]),
            AiResponse(text="Done."),
        ]
    )
    runner = Runner(
        gateway,
        registry_with("lookup", lambda: "{}"),
        config=RunnerConfig(soft_tool_limit=1, hard_tool_limit=10, max_turns=5),
    )

    run(runner.run("system", "user"))

    assert any(
        entry.event_type == "guardrail"
        and entry.data["guardrail_type"] == "soft_tool_limit"
        for entry in runner.log.entries
    )
    guardrail_message = gateway.requests[1].messages[-1]
    assert guardrail_message.role == "system"
    assert "Start wrapping up" in guardrail_message.content


def test_runner_hard_guardrail() -> None:
    gateway = FakeGateway(
        [
            AiResponse(tool_calls=[tool_call("lookup")]),
            AiResponse(text="Done."),
        ]
    )
    runner = Runner(
        gateway,
        registry_with("lookup", lambda: "{}"),
        config=RunnerConfig(soft_tool_limit=1, hard_tool_limit=1, max_turns=5),
    )

    run(runner.run("system", "user"))

    assert any(
        entry.event_type == "guardrail"
        and entry.data["guardrail_type"] == "hard_tool_limit"
        for entry in runner.log.entries
    )
    guardrail_message = gateway.requests[1].messages[-1]
    assert guardrail_message.role == "system"
    assert "HARD LIMIT REACHED" in guardrail_message.content


def test_runner_procedure_replacement() -> None:
    gateway = FakeGateway(
        [
            AiResponse(
                tool_calls=[
                    tool_call("load_procedure", {"name": "research"}, "call_1")
                ]
            ),
            AiResponse(
                tool_calls=[
                    tool_call("load_procedure", {"name": "drafting"}, "call_2")
                ]
            ),
            AiResponse(text="Done."),
        ]
    )
    runner = Runner(
        gateway,
        registry_with("load_procedure", lambda *, name: f"# {name.title()}"),
    )

    run(runner.run("system", "user"))

    third_request_messages = gateway.requests[2].messages
    procedure_messages = [
        message
        for message in third_request_messages
        if isinstance(message, ToolResultMessage)
        and message.name == "load_procedure"
    ]
    assert len(procedure_messages) == 1
    assert procedure_messages[0].tool_call_id == "call_2"
    assert procedure_messages[0].content == "# Drafting"


def test_runner_max_turns() -> None:
    gateway = FakeGateway(
        [
            AiResponse(tool_calls=[tool_call("lookup", call_id="call_1")]),
            AiResponse(tool_calls=[tool_call("lookup", call_id="call_2")]),
            AiResponse(tool_calls=[tool_call("lookup", call_id="call_3")]),
        ]
    )
    runner = Runner(
        gateway,
        registry_with("lookup", lambda: "{}"),
        config=RunnerConfig(max_turns=2),
    )

    output = run(runner.run("system", "user"))

    assert output.run_log_summary["total_turns"] == 2
    assert output.run_log_summary["total_tool_calls"] == 2
    assert len(gateway.requests) == 2
