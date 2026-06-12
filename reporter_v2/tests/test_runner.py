"""Tests for the reporter v2 runner loop."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from reporter_v2.runner.models import ToolCall
from reporter_v2.runner.runner import Runner
from reporter_v2.runner.state import ProcedureHistoryMode, RunnerConfig
from reporter_v2.runner.tools.context import ToolContext
from reporter_v2.runner.tools.registry import ToolRegistry


class FakeCompletion:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        if not self.responses:
            return make_response()
        return self.responses.pop(0)


def make_response(
    *,
    text: str | None = None,
    tool_calls: list[ToolCall] | None = None,
    reasoning_content: str | None = None,
) -> Any:
    raw_calls = [
        SimpleNamespace(
            id=call.id,
            function=SimpleNamespace(
                name=call.name,
                arguments=json.dumps(call.arguments),
            ),
        )
        for call in tool_calls or []
    ]
    message = SimpleNamespace(
        content=text,
        reasoning_content=reasoning_content,
        tool_calls=raw_calls,
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def tool_def(name: str, description: str = "Test tool") -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": {}},
        },
    }


def registry_with(
    name: str,
    handler: Callable[..., Any],
    *,
    description: str = "Test tool",
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(name, handler, tool_def(name, description))
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
    assert registry.tool_specs == [tool_def("lookup")]
    assert registry.get_handler("lookup") is not None
    assert registry.get_handler("missing") is None


def test_runner_context_tool_dispatch_updates_turn() -> None:
    seen_turns: list[int] = []

    def context_tool(ctx: ToolContext) -> str:
        seen_turns.append(ctx.turn)
        return "{}"

    registry = ToolRegistry()
    registry.register_context_tool("context_tool", context_tool, tool_def("context_tool"))
    complete = FakeCompletion(
        [
            make_response(tool_calls=[tool_call("context_tool")]),
            make_response(text="Done."),
        ]
    )
    runner = Runner(registry, complete=complete)

    run(runner.run("system", "user"))

    assert seen_turns == [1]
    assert runner.tool_context.artifacts is runner.artifacts
    assert runner.tool_context.procedures is runner.procedures
    assert runner.tool_context.log is runner.log


def test_runner_simple_text_response() -> None:
    complete = FakeCompletion([make_response(text="Done.")])
    runner = Runner(ToolRegistry(), complete=complete)

    output = run(runner.run("system", "user"))

    assert output.article == ""
    assert output.run_log_summary["total_turns"] == 1
    assert output.run_log_summary["total_tool_calls"] == 0
    assert runner.log.entries[0].event_type == "model_text"
    assert complete.requests[0]["messages"][0]["role"] == "system"
    assert complete.requests[0]["messages"][1]["role"] == "user"
    assert complete.requests[0]["model"] is None


def test_runner_passes_explicit_model_override() -> None:
    complete = FakeCompletion([make_response(text="Done.")])
    runner = Runner(
        ToolRegistry(),
        complete=complete,
        config=RunnerConfig(model="claude-sonnet-4-6"),
    )

    run(runner.run("system", "user"))

    assert complete.requests[0]["model"] == "claude-sonnet-4-6"


def test_runner_tool_call_dispatch() -> None:
    calls: list[dict[str, Any]] = []

    def handler(*, value: int) -> dict[str, Any]:
        calls.append({"value": value})
        return {"ok": True, "value": value}

    complete = FakeCompletion(
        [
            make_response(tool_calls=[tool_call("lookup", {"value": 7})]),
            make_response(text="Done."),
        ]
    )
    runner = Runner(registry_with("lookup", handler), complete=complete)

    output = run(runner.run("system", "user"))

    assert calls == [{"value": 7}]
    assert output.run_log_summary["total_tool_calls"] == 1
    assert len(complete.requests) == 2
    assistant_message = complete.requests[1]["messages"][-2]
    result_message = complete.requests[1]["messages"][-1]
    assert assistant_message["role"] == "assistant"
    assert assistant_message["tool_calls"][0]["id"] == "call_1"
    assert result_message["role"] == "tool"
    assert result_message["tool_call_id"] == "call_1"
    assert result_message["content"] == '{"ok": true, "value": 7}'


def test_runner_carries_tool_call_history_after_tool_call() -> None:
    complete = FakeCompletion(
        [
            make_response(tool_calls=[tool_call("lookup")]),
            make_response(text="Done."),
        ]
    )
    runner = Runner(registry_with("lookup", lambda: "{}"), complete=complete)

    run(runner.run("system", "user"))

    second_request_messages = complete.requests[1]["messages"]
    assert second_request_messages[-2] == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "lookup", "arguments": "{}"},
            }
        ],
    }
    assert second_request_messages[-1] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "name": "lookup",
        "content": "{}",
    }


def test_runner_preserves_reasoning_content_in_tool_call_history() -> None:
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[tool_call("lookup")],
                reasoning_content="reasoning payload",
            ),
            make_response(text="Done."),
        ]
    )
    runner = Runner(registry_with("lookup", lambda: "{}"), complete=complete)

    run(runner.run("system", "user"))

    assistant_message = complete.requests[1]["messages"][-2]
    assert assistant_message["reasoning_content"] == "reasoning payload"


def test_runner_submit_article_breaks_loop() -> None:
    def submit_article() -> str:
        return '{"ok": true}'

    complete = FakeCompletion(
        [
            make_response(tool_calls=[tool_call("submit_article")]),
            make_response(text="Should not be requested."),
        ]
    )
    runner = Runner(registry_with("submit_article", submit_article), complete=complete)

    output = run(runner.run("system", "user"))

    assert output.run_log_summary["submitted"] is True
    assert output.run_log_summary["total_turns"] == 1
    assert len(complete.requests) == 1


def test_runner_failed_submit_article_does_not_break_loop() -> None:
    def submit_article() -> str:
        return '{"ok": false, "error": "Cannot submit an empty article."}'

    complete = FakeCompletion(
        [
            make_response(tool_calls=[tool_call("submit_article")]),
            make_response(text="Done."),
        ]
    )
    runner = Runner(registry_with("submit_article", submit_article), complete=complete)

    output = run(runner.run("system", "user"))

    assert output.run_log_summary["submitted"] is False
    assert output.run_log_summary["total_turns"] == 2
    assert len(complete.requests) == 2


def test_runner_does_not_limit_tool_calls() -> None:
    calls: list[str] = []

    def lookup() -> str:
        calls.append("lookup")
        return "{}"

    complete = FakeCompletion(
        [
            make_response(tool_calls=[tool_call("lookup", call_id="call_1")]),
            make_response(tool_calls=[tool_call("lookup", call_id="call_2")]),
            make_response(text="Done."),
        ]
    )
    runner = Runner(
        registry_with("lookup", lookup),
        complete=complete,
        config=RunnerConfig(max_turns=5),
    )

    output = run(runner.run("system", "user"))

    assert calls == ["lookup", "lookup"]
    assert output.run_log_summary["total_tool_calls"] == 2
    assert not any(entry.event_type == "guardrail" for entry in runner.log.entries)


def test_runner_procedure_replacement() -> None:
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[
                    tool_call("load_procedure", {"name": "research"}, "call_1")
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call("load_procedure", {"name": "drafting"}, "call_2")
                ]
            ),
            make_response(text="Done."),
        ]
    )
    runner = Runner(
        registry_with("load_procedure", lambda *, name: f"# {name.title()}"),
        complete=complete,
        config=RunnerConfig(procedure_history_mode="replace"),
    )

    run(runner.run("system", "user"))

    third_request_messages = complete.requests[2]["messages"]
    procedure_messages = [
        message
        for message in third_request_messages
        if message.get("role") == "tool" and message.get("name") == "load_procedure"
    ]
    active_procedure_messages = [
        message
        for message in procedure_messages
        if message.get("content") != "[procedure replaced]"
    ]
    assert len(active_procedure_messages) == 1
    assert active_procedure_messages[0]["tool_call_id"] == "call_2"
    assert active_procedure_messages[0]["content"] == "# Drafting"
    assert any(
        message["tool_call_id"] == "call_1"
        and message["content"] == "[procedure replaced]"
        for message in procedure_messages
    )


def test_runner_procedure_append_mode() -> None:
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[
                    tool_call("load_procedure", {"name": "research"}, "call_1")
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call("load_procedure", {"name": "drafting"}, "call_2")
                ]
            ),
            make_response(text="Done."),
        ]
    )
    runner = Runner(
        registry_with("load_procedure", lambda *, name: f"# {name.title()}"),
        complete=complete,
        config=RunnerConfig(procedure_history_mode=ProcedureHistoryMode.APPEND),
    )

    run(runner.run("system", "user"))

    third_request_messages = complete.requests[2]["messages"]
    procedure_messages = [
        message
        for message in third_request_messages
        if message.get("role") == "tool" and message.get("name") == "load_procedure"
    ]
    assert [
        (message["tool_call_id"], message["content"])
        for message in procedure_messages
    ] == [
        ("call_1", "# Research"),
        ("call_2", "# Drafting"),
    ]
    assert all(
        message["content"] != "[procedure replaced]"
        for message in procedure_messages
    )


def test_runner_max_turns() -> None:
    complete = FakeCompletion(
        [
            make_response(tool_calls=[tool_call("lookup", call_id="call_1")]),
            make_response(tool_calls=[tool_call("lookup", call_id="call_2")]),
            make_response(tool_calls=[tool_call("lookup", call_id="call_3")]),
        ]
    )
    runner = Runner(
        registry_with("lookup", lambda: "{}"),
        complete=complete,
        config=RunnerConfig(max_turns=2),
    )

    output = run(runner.run("system", "user"))

    assert output.run_log_summary["total_turns"] == 2
    assert output.run_log_summary["total_tool_calls"] == 2
    assert len(complete.requests) == 2
