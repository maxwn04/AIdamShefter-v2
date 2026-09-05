"""Tests for the reporter v2 runner loop."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from backend.resources.memory.search_documents import SearchDocumentQuery
from backend.services.memory import MemoryRetrievalResult
from backend.services.reporter.runner.completion import CompletionClient, CompletionSettings
from backend.services.reporter.runner.memory_closeout import (
    MemoryCloseoutIncompleteError,
    MemoryCloseoutState,
)
from backend.services.reporter.runner.models import ToolCall, ToolExecutionResult
from backend.services.reporter.runner.evidence import EvidenceRecord
from backend.services.reporter.runner.recording import (
    ArtifactMutation,
    GenerationProgress,
    ToolExecutionFinish,
    ToolExecutionStart,
)
from backend.services.reporter.runner.runner import Runner, RunnerRecordingError
from backend.services.reporter.runner.state import (
    ArtifactStore,
    RunnerConfig,
)
from backend.services.reporter.runner.tools.artifact_tools import register_artifact_tools
from backend.services.reporter.runner.tools.brief_tools import (
    save_fact,
    save_memory_callback,
    save_storyline,
    set_outline,
)
from backend.services.reporter.runner.tools.context import ToolContext
from backend.services.reporter.runner.tools.memory_presentation import (
    MemoryPresentationAdapter,
)
from backend.services.reporter.runner.tools.memory_closeout_tools import (
    register_memory_closeout_tools,
)
from backend.services.reporter.runner.tools.procedure_tools import (
    register_procedure_tools,
)
from backend.services.reporter.runner.tools.registry import ToolRegistry


class RecordingProbe:
    def __init__(
        self,
        *,
        fail_begin: bool = False,
        fail_finish: bool = False,
        fail_progress: bool = False,
        fail_artifact: bool = False,
    ) -> None:
        self.fail_begin = fail_begin
        self.fail_finish = fail_finish
        self.fail_progress = fail_progress
        self.fail_artifact = fail_artifact
        self.started: list[tuple[UUID, ToolExecutionStart]] = []
        self.finished: list[tuple[UUID, ToolExecutionFinish]] = []
        self.progress: list[GenerationProgress] = []
        self.artifact_mutations: list[ArtifactMutation] = []

    def begin_tool_execution(self, execution: ToolExecutionStart) -> UUID:
        if self.fail_begin:
            raise RuntimeError("database unavailable")
        execution_id = uuid4()
        self.started.append((execution_id, execution))
        return execution_id

    def finish_tool_execution(
        self,
        execution_id: UUID,
        result: ToolExecutionFinish,
    ) -> None:
        if self.fail_finish:
            raise RuntimeError("database unavailable")
        self.finished.append((execution_id, result))

    def update_progress(self, progress: GenerationProgress) -> None:
        if self.fail_progress:
            raise RuntimeError("database unavailable")
        self.progress.append(progress)

    def record_artifact_mutation(self, mutation: ArtifactMutation) -> UUID:
        if self.fail_artifact:
            raise RuntimeError("database unavailable")
        self.artifact_mutations.append(mutation)
        return uuid4()


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
    registry.register(name, handler, tool_def(name, description), "test-v1")
    return registry


def closeout_runner(
    complete: FakeCompletion,
    *,
    max_turns: int = 60,
    proposals: list[Any] | None = None,
    register_write: bool = False,
    recorder: RecordingProbe | None = None,
) -> tuple[Runner, MemoryCloseoutState]:
    buffered = proposals if proposals is not None else []
    registry = ToolRegistry()
    registry.register(
        "submit_artifact",
        lambda **_: '{"ok": true}',
        tool_def("submit_artifact"),
        "test-v1",
    )
    if register_write:
        def save_memory_event() -> dict[str, Any]:
            buffered.append(
                SimpleNamespace(
                    proposal_id=uuid4(),
                    kind=SimpleNamespace(value="event"),
                    operation="create",
                )
            )
            return {"ok": True, "saved": True}

        registry.register(
            "save_memory_event",
            save_memory_event,
            tool_def("save_memory_event"),
            "test-v1",
        )
    register_memory_closeout_tools(registry)
    state = MemoryCloseoutState(
        procedure="# Closeout",
        memory_writes_enabled=True,
        proposal_snapshot=lambda: tuple(buffered),  # type: ignore[arg-type]
    )
    return (
        Runner(
            registry,
            complete=complete,
            config=RunnerConfig(max_turns=max_turns),
            memory_closeout=state,
            recorder=recorder,
        ),
        state,
    )


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
    assert registry.tool_implementation_versions == [("lookup", "test-v1")]
    assert registry.get_implementation_version("lookup") == "test-v1"
    assert registry.get_implementation_version("missing") is None
    assert registry.get_handler("lookup") is not None
    assert registry.get_handler("missing") is None


def test_tool_registry_requires_an_explicit_implementation_version() -> None:
    registry = ToolRegistry()

    for invalid in ("", " untrimmed"):
        with pytest.raises(ValueError, match="implementation version"):
            registry.register("lookup", lambda: "{}", tool_def("lookup"), invalid)


def test_runner_context_tool_dispatch_updates_turn() -> None:
    seen_turns: list[int] = []

    def context_tool(ctx: ToolContext) -> str:
        seen_turns.append(ctx.turn)
        return "{}"

    registry = ToolRegistry()
    registry.register_context_tool(
        "context_tool",
        context_tool,
        tool_def("context_tool"),
        "test-v1",
    )
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

    assert output.submitted_path is None
    assert output.artifacts == ()
    assert output.run_log_summary["total_turns"] == 1
    assert output.run_log_summary["total_tool_calls"] == 0
    assert output.run_log_summary["brief"] == {
        "revision": 0,
        "projection_revision": None,
        "fact_count": 0,
        "callback_count": 0,
        "storyline_count": 0,
        "outline_section_count": 0,
        "stale_callback_ids": [],
        "stale_storyline_ids": [],
        "outline_stale": False,
        "readiness_warnings": [
            "no_traceable_facts",
            "no_storylines",
            "no_outline",
        ],
        "first_fact_turn": None,
        "first_storyline_turn": None,
        "first_draft_turn": None,
        "submission_turn": None,
    }
    assert runner.log.entries[0].event_type == "model_text"
    assert complete.requests[0]["messages"][0]["role"] == "system"
    assert complete.requests[0]["messages"][1]["role"] == "user"
    assert complete.requests[0]["model"] is None
    assert "turn_number" not in complete.requests[0]


def test_runner_places_initial_context_between_system_and_assignment() -> None:
    complete = FakeCompletion([make_response(text="Done.")])
    runner = Runner(ToolRegistry(), complete=complete)

    run(
        runner.run(
            "system",
            "assignment",
            initial_context=("first context", "second context"),
        )
    )

    assert complete.requests[0]["messages"][:4] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "first context"},
        {"role": "user", "content": "second context"},
        {"role": "user", "content": "assignment"},
    ]


def test_runner_brief_summary_propagates_stale_dependency_warnings() -> None:
    runner = Runner(
        ToolRegistry(),
        complete=FakeCompletion([make_response(text="Done.")]),
    )
    ctx = runner.tool_context
    old = EvidenceRecord("old.r0", "old", "transactions", "found", fields={"week": 3})
    current = EvidenceRecord("current.r0", "current", "team_game", "found", fields={"touchdowns": 2})
    ctx.evidence.register("old", (old,))
    ctx.evidence.register("current", (current,))
    def selected(record, field):
        return {"ref": record.ref, "field": field, "value": record.fields[field],
                "subject": None, "season": None, "week_from": None, "week_to": None}
    ctx.turn = 1
    save_fact(
        ctx,
        id="fact_old",
        claim_text="The Week 3 trade happened.",
        data_refs=[old.ref], bindings=[selected(old, "week")],
    )
    ctx.turn = 2
    save_fact(
        ctx,
        id="fact_current",
        claim_text="The player decided the Week 8 rematch.",
        data_refs=[current.ref], bindings=[selected(current, "touchdowns")],
    )
    ctx.turn = 3
    save_memory_callback(
        ctx,
        id="callback_trade_regret",
        callback_type="trade_regret",
        claim_text="The trade backfired in the rematch.",
        old_event_fact_id="fact_old",
        current_event_fact_id="fact_current",
        why_now="The former player decided the rematch.",
    )
    ctx.turn = 4
    save_storyline(
        ctx,
        id="story_trade_regret",
        headline="The trade comes due",
        summary="The old move changed the current matchup.",
        supporting_fact_ids=["fact_old", "fact_current"],
    )
    ctx.turn = 5
    set_outline(
        ctx,
        sections=[
            {
                "title": "Lead",
                "required_fact_ids": ["fact_current"],
                "storyline_ids": ["story_trade_regret"],
            }
        ],
    )
    ctx.turn = 6
    save_fact(
        ctx,
        id="fact_current",
        claim_text="The player scored twice in the Week 8 rematch.",
        data_refs=[current.ref], bindings=[selected(current, "touchdowns")],
        numbers={"touchdowns": 2},
    )

    summary = run(runner.run("system", "user")).run_log_summary["brief"]

    assert summary["revision"] == 6
    assert summary["projection_revision"] == 6
    assert summary["stale_callback_ids"] == ["callback_trade_regret"]
    assert summary["stale_storyline_ids"] == ["story_trade_regret"]
    assert summary["outline_stale"] is True
    assert summary["readiness_warnings"] == [
        "stale_callbacks",
        "stale_storylines",
        "stale_outline",
    ]
    assert summary["first_fact_turn"] == 1
    assert summary["first_storyline_turn"] == 4


def test_runner_passes_explicit_model_override() -> None:
    complete = FakeCompletion([make_response(text="Done.")])
    runner = Runner(
        ToolRegistry(),
        client=CompletionClient(
            complete,
            CompletionSettings(model="claude-sonnet-4-6"),
        ),
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


@pytest.mark.parametrize(
    ("raw_result", "expected_text"),
    [
        ("plain text", "plain text"),
        (7, "7"),
        (["one", 2], '["one", 2]'),
        (None, "null"),
    ],
)
def test_runner_keeps_raw_tool_results_compatible(
    raw_result: Any,
    expected_text: str,
) -> None:
    complete = FakeCompletion(
        [
            make_response(tool_calls=[tool_call("lookup")]),
            make_response(text="Done."),
        ]
    )
    recorder = RecordingProbe()
    runner = Runner(
        registry_with("lookup", lambda: raw_result),
        complete=complete,
        recorder=recorder,
    )

    run(runner.run("system", "user"))

    recorded = recorder.finished[0][1]
    assert recorded.result == raw_result
    assert recorded.result_text == expected_text
    assert recorded.metadata == {}
    assert complete.requests[1]["messages"][-1]["content"] == expected_text


def test_runner_hides_tool_execution_metadata_from_model_messages() -> None:
    logical_result = {"memories": [{"headline": "A callback"}]}
    metadata = {
        "bindings": [{"item_id": "private-id", "result_ordinal": 0}],
        "candidate_count": 4,
    }
    complete = FakeCompletion(
        [
            make_response(tool_calls=[tool_call("lookup")]),
            make_response(text="Done."),
        ]
    )
    recorder = RecordingProbe()
    runner = Runner(
        registry_with(
            "lookup",
            lambda: ToolExecutionResult(result=logical_result, metadata=metadata),
        ),
        complete=complete,
        recorder=recorder,
    )

    run(runner.run("system", "user"))

    recorded = recorder.finished[0][1]
    sent_text = complete.requests[1]["messages"][-1]["content"]
    assert recorded.result == logical_result
    assert recorded.result_text == sent_text
    assert recorded.metadata == metadata
    assert "private-id" not in sent_text


def test_runner_records_exact_semantic_memory_result_with_hidden_bindings() -> None:
    revision_id = uuid4()
    presentation = MemoryPresentationAdapter(SimpleNamespace()).present(  # type: ignore[arg-type]
        MemoryRetrievalResult(
            competition_id=uuid4(),
            revision_id=revision_id,
            matches=(),
        ),
        query=SearchDocumentQuery(text="playoff push", limit=9),
        limit=8,
    )
    complete = FakeCompletion(
        [
            make_response(tool_calls=[tool_call("search_memory")]),
            make_response(text="Done."),
        ]
    )
    recorder = RecordingProbe()
    runner = Runner(
        registry_with("search_memory", lambda: presentation),
        complete=complete,
        recorder=recorder,
    )

    run(runner.run("system", "user"))

    recorded = recorder.finished[0][1]
    sent_text = complete.requests[1]["messages"][-1]["content"]
    assert recorded.result == presentation.result
    assert recorded.result_text == sent_text
    assert recorded.metadata == presentation.metadata
    assert str(revision_id) not in sent_text
    assert "pinned_revision_id" not in sent_text


def test_runner_records_parallel_tools_in_provider_order_with_exact_results() -> None:
    async def handler(*, value: int, delay: float) -> dict[str, Any]:
        await asyncio.sleep(delay)
        return {"ok": value != 2, "value": value}

    calls = [
        tool_call("lookup", {"value": 1, "delay": 0.02}, "call_1"),
        tool_call("lookup", {"value": 2, "delay": 0.0}, "call_2"),
    ]
    complete = FakeCompletion(
        [make_response(tool_calls=calls), make_response(text="Done.")]
    )
    recorder = RecordingProbe()
    runner = Runner(
        registry_with("lookup", handler),
        complete=complete,
        recorder=recorder,
    )

    run(runner.run("system", "user"))

    assert [event.tool_ordinal for _, event in recorder.started] == [0, 1]
    assert [event.provider_tool_call_id for _, event in recorder.started] == [
        "call_1",
        "call_2",
    ]
    assert [result.status for _, result in recorder.finished] == [
        "succeeded",
        "succeeded",
    ]
    persisted_by_id = {
        execution_id: result.result_text
        for execution_id, result in recorder.finished
    }
    persisted_in_provider_order = [
        persisted_by_id[execution_id] for execution_id, _ in recorder.started
    ]
    sent_results = [
        message["content"]
        for message in complete.requests[1]["messages"]
        if message["role"] == "tool"
    ]
    assert persisted_in_provider_order == sent_results
    assert json.loads(sent_results[1]) == {"ok": False, "value": 2}


def test_runner_records_unknown_tools_and_sanitized_handler_exceptions() -> None:
    def explode() -> None:
        raise RuntimeError("Bearer secret-token api_key=top-secret")

    registry = registry_with("explode", explode)
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[tool_call("missing"), tool_call("explode", call_id="call_2")]
            ),
            make_response(text="Done."),
        ]
    )
    recorder = RecordingProbe()
    runner = Runner(registry, complete=complete, recorder=recorder)

    run(runner.run("system", "user"))

    starts = [event for _, event in recorder.started]
    assert starts[0].implementation_version == "unregistered-v1"
    assert starts[1].implementation_version == "test-v1"
    results = [result for _, result in recorder.finished]
    assert [result.status for result in results] == ["failed", "failed"]
    assert results[0].error == {
        "type": "UnknownToolError",
        "message": "Unknown tool: missing",
    }
    assert results[1].error is not None
    assert results[1].error["type"] == "RuntimeError"
    assert "secret-token" not in str(results[1].error)
    assert "top-secret" not in str(results[1].error)
    sent = [
        message["content"]
        for message in complete.requests[1]["messages"]
        if message["role"] == "tool"
    ]
    assert sent == [result.result_text for result in results]


def test_runner_records_tool_cancellation_and_reraises() -> None:
    started = asyncio.Event()

    async def wait_forever() -> None:
        started.set()
        await asyncio.Event().wait()

    async def scenario() -> None:
        recorder = RecordingProbe()
        runner = Runner(
            registry_with("wait", wait_forever),
            complete=FakeCompletion([]),
            recorder=recorder,
        )
        task = asyncio.create_task(runner._execute_tool(tool_call("wait"), 1, 0))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert recorder.finished[0][1] == ToolExecutionFinish(status="cancelled")

    run(scenario())


def test_runner_records_bounded_turn_and_phase_progress() -> None:
    registry = ToolRegistry()
    register_artifact_tools(registry)
    register_procedure_tools(registry)
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[tool_call("load_procedure", {"name": "research"})]
            ),
            make_response(text="Done."),
        ]
    )
    recorder = RecordingProbe()
    runner = Runner(registry, complete=complete, recorder=recorder)

    run(runner.run("system", "user"))

    assert recorder.progress == [
        GenerationProgress(current_turn=1, current_stage="running"),
        GenerationProgress(current_turn=1, current_stage="research"),
        GenerationProgress(current_turn=2, current_stage="research"),
    ]


def test_runner_progress_recording_fails_closed_before_provider_call() -> None:
    complete = FakeCompletion([make_response(text="Done.")])
    runner = Runner(
        ToolRegistry(),
        complete=complete,
        recorder=RecordingProbe(fail_progress=True),
    )

    with pytest.raises(RunnerRecordingError, match="progress"):
        run(runner.run("system", "user"))

    assert complete.requests == []


def test_runner_tool_recording_fails_closed_around_handler() -> None:
    calls: list[str] = []

    def handler() -> str:
        calls.append("called")
        return "result"

    responses = [
        make_response(tool_calls=[tool_call("lookup")]),
        make_response(text="Done."),
    ]
    begin_complete = FakeCompletion(list(responses))
    begin_runner = Runner(
        registry_with("lookup", handler),
        complete=begin_complete,
        recorder=RecordingProbe(fail_begin=True),
    )
    with pytest.raises(RunnerRecordingError, match="begin"):
        run(begin_runner.run("system", "user"))
    assert calls == []
    assert len(begin_complete.requests) == 1

    finish_complete = FakeCompletion(list(responses))
    finish_runner = Runner(
        registry_with("lookup", handler),
        complete=finish_complete,
        recorder=RecordingProbe(fail_finish=True),
    )
    with pytest.raises(RunnerRecordingError, match="finish"):
        run(finish_runner.run("system", "user"))
    assert calls == ["called"]
    assert len(finish_complete.requests) == 1


def test_runner_artifact_turn_flush_fails_closed() -> None:
    registry = ToolRegistry()
    register_artifact_tools(registry)
    recorder = RecordingProbe(fail_artifact=True)
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[
                    tool_call(
                        "create_artifact",
                        {"path": "article.md", "content": "Draft"},
                    )
                ]
            )
        ]
    )
    runner = Runner(registry, complete=complete, recorder=recorder)

    with pytest.raises(RunnerRecordingError, match="artifact"):
        run(runner.run("system", "user"))

    assert runner.artifacts.read("article.md").content == "Draft"
    assert recorder.finished[-1][1].status == "succeeded"
    assert recorder.artifact_mutations == []


def test_runner_coalesces_artifact_mutations_by_turn() -> None:
    registry = ToolRegistry()
    register_artifact_tools(registry)

    def compose_draft(ctx: ToolContext) -> str:
        ctx.artifacts.create(
            "article.md",
            "Alpha beta",
            on_change=ctx.record_artifact_mutation,
        )
        ctx.artifacts.edit(
            "article.md",
            old_text="beta",
            new_text="gamma",
            expected_revision=1,
            on_change=ctx.record_artifact_mutation,
        )
        return '{"ok": true}'

    registry.register_context_tool(
        "compose_draft",
        compose_draft,
        tool_def("compose_draft"),
        "test-v1",
    )
    recorder = RecordingProbe()
    complete = FakeCompletion(
        [
            make_response(tool_calls=[tool_call("compose_draft")]),
            make_response(
                tool_calls=[
                    tool_call(
                        "edit_artifact",
                        {
                            "path": "article.md",
                            "old_text": "Alpha",
                            "new_text": "Delta",
                            "expected_revision": 2,
                        },
                    )
                ]
            ),
            make_response(text="Done."),
        ]
    )
    runner = Runner(registry, complete=complete, recorder=recorder)

    output = run(runner.run("system", "user"))

    assert [(item.revision, item.content) for item in recorder.artifact_mutations] == [
        (1, "Alpha gamma"),
        (2, "Delta gamma"),
    ]
    assert output.artifacts[0].revision == 2
    assert output.artifacts[0].content == "Delta gamma"


def test_runner_parallel_artifact_provenance_is_invocation_local() -> None:
    registry = ToolRegistry()
    register_artifact_tools(registry)
    recorder = RecordingProbe()
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[
                    tool_call(
                        "create_artifact",
                        {"path": "one.md", "content": "One"},
                        "create_1",
                    ),
                    tool_call(
                        "create_artifact",
                        {"path": "two.md", "content": "Two"},
                        "create_2",
                    ),
                ]
            ),
            make_response(text="Done."),
        ]
    )
    runner = Runner(registry, complete=complete, recorder=recorder)

    run(runner.run("system", "user"))

    started_ids = [execution_id for execution_id, _ in recorder.started]
    assert [
        mutation.source_tool_call_id for mutation in recorder.artifact_mutations
    ] == started_ids


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


def test_runner_submit_artifact_breaks_loop() -> None:
    def submit_artifact(*, path: str, expected_revision: int) -> str:
        assert (path, expected_revision) == ("article.md", 2)
        return '{"ok": true}'

    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[
                    tool_call(
                        "submit_artifact",
                        {"path": "article.md", "expected_revision": 2},
                    )
                ]
            ),
            make_response(text="Should not be requested."),
        ]
    )
    runner = Runner(
        registry_with("submit_artifact", submit_artifact), complete=complete
    )

    output = run(runner.run("system", "user"))

    assert output.submitted_path is None
    assert output.run_log_summary["submitted"] is True
    assert output.run_log_summary["total_turns"] == 1
    assert len(complete.requests) == 1


def test_runner_failed_submit_artifact_does_not_break_loop() -> None:
    def submit_artifact(*, path: str, expected_revision: int) -> str:
        del path, expected_revision
        return '{"ok": false, "error": {"code": "empty_submission"}}'

    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[
                    tool_call(
                        "submit_artifact",
                        {"path": "article.md", "expected_revision": 1},
                    )
                ]
            ),
            make_response(text="Done."),
        ]
    )
    runner = Runner(
        registry_with("submit_artifact", submit_artifact), complete=complete
    )

    output = run(runner.run("system", "user"))

    assert output.submitted_path is None
    assert output.run_log_summary["submitted"] is False
    assert output.run_log_summary["total_turns"] == 2
    assert len(complete.requests) == 2


def test_memory_closeout_rejects_completion_before_submission() -> None:
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[tool_call("complete_memory_review", call_id="early")]
            ),
            make_response(
                tool_calls=[tool_call("submit_artifact", call_id="submit")]
            ),
            make_response(
                tool_calls=[tool_call("complete_memory_review", call_id="complete")]
            ),
        ]
    )
    runner, state = closeout_runner(complete)

    output = run(runner.run("system", "user"))

    early_result = next(
        json.loads(message["content"])
        for message in complete.requests[1]["messages"]
        if message.get("tool_call_id") == "early"
    )
    assert early_result["error"]["code"] == "article_not_submitted"
    assert state.memory_review_completed is True
    assert output.run_log_summary["memory_closeout"]["status"] == "completed"
    assert output.run_log_summary["memory_closeout"]["no_op"] is True


def test_submit_and_complete_in_same_batch_cannot_skip_closeout() -> None:
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[
                    tool_call("submit_artifact", call_id="submit"),
                    tool_call("complete_memory_review", call_id="too-soon"),
                ]
            ),
            make_response(
                tool_calls=[tool_call("complete_memory_review", call_id="complete")]
            ),
        ]
    )
    runner, state = closeout_runner(complete)

    output = run(runner.run("system", "user"))

    first_batch_results = {
        message["tool_call_id"]: json.loads(message["content"])
        for message in complete.requests[1]["messages"]
        if message["role"] == "tool"
    }
    assert first_batch_results["too-soon"]["error"]["code"] == (
        "article_not_submitted"
    )
    assert state.closeout_turns_used == 1
    assert output.run_log_summary["memory_closeout"]["status"] == "completed"


def test_closeout_continues_after_model_text_with_stable_tool_definitions() -> None:
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[tool_call("submit_artifact", call_id="submit")]
            ),
            make_response(text="I reviewed the final article."),
            make_response(
                tool_calls=[tool_call("complete_memory_review", call_id="complete")]
            ),
        ]
    )
    recorder = RecordingProbe()
    runner, _ = closeout_runner(complete, recorder=recorder)

    output = run(runner.run("system", "user"))

    assert output.run_log_summary["total_turns"] == 3
    assert output.run_log_summary["memory_closeout"]["turns_used"] == 2
    assert all(
        request["tools"] == complete.requests[0]["tools"]
        for request in complete.requests
    )
    assert GenerationProgress(
        current_turn=1,
        current_stage="memory_closeout",
    ) in recorder.progress
    assert recorder.progress[-1] == GenerationProgress(
        current_turn=3,
        current_stage="memory_closeout",
    )


def test_closeout_counts_parallel_write_before_completion() -> None:
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[tool_call("submit_artifact", call_id="submit")]
            ),
            make_response(
                tool_calls=[
                    tool_call("complete_memory_review", call_id="complete"),
                    tool_call("save_memory_event", call_id="save"),
                ]
            ),
        ]
    )
    recorder = RecordingProbe()
    runner, _ = closeout_runner(
        complete,
        register_write=True,
        recorder=recorder,
    )

    output = run(runner.run("system", "user"))

    summary = output.run_log_summary["memory_closeout"]
    assert summary["no_op"] is False
    assert summary["proposal_counts"] == {
        "total": 1,
        "by_kind": {"event": 1},
        "by_operation": {"create": 1},
    }
    completion_entry = next(
        entry
        for entry in output.run_log_entries
        if entry["event_type"] == "memory_closeout"
        and entry["data"]["event"] == "memory_review_completed"
    )
    assert completion_entry["data"]["outcome"] == "proposals_saved"
    completion_execution_id = next(
        execution_id
        for execution_id, started in recorder.started
        if started.tool_name == "complete_memory_review"
    )
    recorded = next(
        result
        for execution_id, result in recorder.finished
        if execution_id == completion_execution_id
    )
    assert recorded.result == {
        "ok": True,
        "memory_review_completed": True,
        "already_completed": False,
        "outcome": "proposals_saved",
        "proposal_counts": summary["proposal_counts"],
    }
    assert recorded.result_text == json.dumps(recorded.result)
    assert recorded.metadata == {}


def test_last_normal_turn_submission_gets_six_closeout_turns() -> None:
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[tool_call("submit_artifact", call_id="submit")]
            ),
            *[make_response(text=f"Review note {index}") for index in range(5)],
            make_response(
                tool_calls=[tool_call("complete_memory_review", call_id="complete")]
            ),
        ]
    )
    runner, _ = closeout_runner(complete, max_turns=1)

    output = run(runner.run("system", "user"))

    assert len(complete.requests) == 7
    assert output.run_log_summary["total_turns"] == 7
    assert output.run_log_summary["memory_closeout"]["turns_used"] == 6
    assert output.run_log_summary["memory_closeout"]["completion_turn"] == 7


def test_closeout_exhaustion_is_fatal_and_records_progress() -> None:
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[tool_call("submit_artifact", call_id="submit")]
            ),
            *[make_response(text=f"Incomplete {index}") for index in range(6)],
        ]
    )
    recorder = RecordingProbe()
    runner, state = closeout_runner(
        complete,
        max_turns=1,
        recorder=recorder,
    )

    with pytest.raises(MemoryCloseoutIncompleteError, match="six-turn"):
        run(runner.run("system", "user"))

    assert len(complete.requests) == 7
    assert state.exhausted is True
    assert recorder.progress[-1] == GenerationProgress(
        current_turn=7,
        current_stage="memory_closeout_exhausted",
    )
    assert runner.log.entries[-1].data["event"] == "limit_exhausted"


def test_runner_parallel_edits_with_same_revision_allow_exactly_one_success() -> None:
    artifacts = ArtifactStore()
    artifacts.create("article.md", "Alpha beta")
    registry = ToolRegistry()
    register_artifact_tools(registry)
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[
                    tool_call(
                        "edit_artifact",
                        {
                            "path": "article.md",
                            "old_text": "Alpha",
                            "new_text": "First",
                            "expected_revision": 1,
                        },
                        "edit_1",
                    ),
                    tool_call(
                        "edit_artifact",
                        {
                            "path": "article.md",
                            "old_text": "beta",
                            "new_text": "Second",
                            "expected_revision": 1,
                        },
                        "edit_2",
                    ),
                ]
            ),
            make_response(text="Done."),
        ]
    )
    runner = Runner(registry, complete=complete, artifacts=artifacts)

    output = run(runner.run("system", "user"))

    article = output.artifacts[0]
    assert article.revision == 2
    assert article.content == "First beta"
    tool_results = [
        json.loads(message["content"])
        for message in complete.requests[1]["messages"]
        if message["role"] == "tool"
    ]
    assert tool_results[0]["ok"] is True
    assert tool_results[0]["artifact"]["revision"] == 2
    assert tool_results[1]["ok"] is False
    assert tool_results[1]["error"]["code"] == "revision_conflict"
    assert tool_results[1]["error"]["current_revision"] == 2


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


def test_runner_appends_procedure_history_by_default() -> None:
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
        config=RunnerConfig(),
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
