"""Tests for the durable generation AI-call recorder adapter."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest

from backend.resources.reporting.ai_calls import AICallManager
from backend.resources.reporting.generations import GenerationManager
from backend.resources.reporting.tool_calls import ToolCallManager
from backend.services.generations import GenerationExecutionRecorder
from backend.services.reporter.runner.recording import (
    GenerationProgress,
    ModelAttemptFinish,
    ModelAttemptStart,
    RecordedTokenUsage,
    ToolExecutionFinish,
    ToolExecutionStart,
)


class FakeAICallManager:
    def __init__(self) -> None:
        self.begun = []
        self.finished = []
        self.turns: dict[UUID, int] = {}

    def begin_ai_call(self, command):
        call_id = uuid4()
        self.begun.append(command)
        self.turns[call_id] = command.turn_number
        return SimpleNamespace(id=call_id)

    def finish_ai_call(self, command):
        self.finished.append(command)
        return SimpleNamespace(
            id=command.ai_call_id,
            turn_number=self.turns[command.ai_call_id],
            status=SimpleNamespace(value=command.status.value),
        )


class FakeToolCallManager:
    def __init__(self) -> None:
        self.begun = []
        self.finished = []

    def begin_tool_call(self, command):
        self.begun.append(command)
        return SimpleNamespace(id=uuid4())

    def finish_tool_call(self, command):
        self.finished.append(command)
        return SimpleNamespace(id=command.tool_call_id)


class FakeGenerationManager:
    def __init__(self) -> None:
        self.progress = []

    def update_progress(self, command):
        self.progress.append(command)
        return SimpleNamespace(id=command.generation_id)


def make_recorder(
    generation_id: UUID | None = None,
) -> tuple[
    GenerationExecutionRecorder,
    FakeAICallManager,
    FakeToolCallManager,
    FakeGenerationManager,
]:
    ai_calls = FakeAICallManager()
    tool_calls = FakeToolCallManager()
    generations = FakeGenerationManager()
    recorder = GenerationExecutionRecorder(
        generation_id or uuid4(),
        cast(AICallManager, ai_calls),
        cast(ToolCallManager, tool_calls),
        cast(GenerationManager, generations),
    )
    return recorder, ai_calls, tool_calls, generations


def test_recorder_maps_reporter_events_and_retains_success_identity() -> None:
    generation_id = uuid4()
    recorder, manager, _, _ = make_recorder(generation_id)
    attempt_id = recorder.begin_model_attempt(
        ModelAttemptStart(
            turn_number=2,
            requested_provider="openai",
            requested_model="openai/model",
            input_messages=({"role": "user", "content": "hello"},),
            tool_definitions=({"type": "function", "name": "lookup"},),
            request_parameters={"temperature": 0.2},
        )
    )
    recorder.finish_model_attempt(
        attempt_id,
        ModelAttemptFinish(
            status="succeeded",
            actual_provider="openai",
            actual_model="model",
            provider_response={"id": "response-1"},
            usage=RecordedTokenUsage(
                input_tokens=12,
                output_tokens=5,
                raw_provider_usage={"prompt_tokens": 12},
            ),
        ),
    )

    assert recorder.generation_id == generation_id
    assert manager.begun[0].generation_id == generation_id
    assert manager.begun[0].turn_number == 2
    assert manager.finished[0].usage.input_tokens == 12
    assert recorder.successful_ai_call_id(2) == attempt_id
    assert recorder.successful_ai_call_id(3) is None


def test_failed_attempt_does_not_become_successful_identity() -> None:
    recorder, _, _, _ = make_recorder()
    attempt_id = recorder.begin_model_attempt(
        ModelAttemptStart(
            turn_number=1,
            requested_provider=None,
            requested_model="model",
            input_messages=(),
            tool_definitions=(),
            request_parameters={},
        )
    )
    recorder.finish_model_attempt(
        attempt_id,
        ModelAttemptFinish(
            status="retryable_error",
            error={"type": "TimeoutError", "message": "timeout"},
        ),
    )

    assert recorder.successful_ai_call_id(1) is None


def test_recorder_maps_tool_execution_to_successful_turn_provenance() -> None:
    generation_id = uuid4()
    recorder, _, tool_calls, _ = make_recorder(generation_id)
    attempt_id = recorder.begin_model_attempt(
        ModelAttemptStart(
            turn_number=4,
            requested_provider="openai",
            requested_model="model",
            input_messages=(),
            tool_definitions=(),
            request_parameters={},
        )
    )
    recorder.finish_model_attempt(
        attempt_id,
        ModelAttemptFinish(
            status="succeeded",
            actual_model="model",
            provider_response={"choices": []},
        ),
    )

    execution_id = recorder.begin_tool_execution(
        ToolExecutionStart(
            turn_number=4,
            tool_ordinal=2,
            provider_tool_call_id="provider-call-2",
            tool_name="lookup",
            implementation_version="lookup-v3",
            arguments={"week": 8},
        )
    )
    recorder.finish_tool_execution(
        execution_id,
        ToolExecutionFinish(
            status="succeeded",
            full_result_text='{"found": true}',
            structured_result={"found": True},
        ),
    )

    begun = tool_calls.begun[0]
    assert begun.generation_id == generation_id
    assert begun.ai_call_id == attempt_id
    assert begun.tool_ordinal == 2
    assert begun.provider_tool_call_id == "provider-call-2"
    assert begun.tool_name == "lookup"
    assert begun.implementation_version == "lookup-v3"
    assert begun.arguments == {"week": 8}
    finished = tool_calls.finished[0]
    assert finished.tool_call_id == execution_id
    assert finished.status.value == "succeeded"
    assert finished.full_result_text == '{"found": true}'
    assert finished.structured_result == {"found": True}


def test_recorder_rejects_tools_without_a_successful_turn() -> None:
    recorder, _, tool_calls, _ = make_recorder()

    with pytest.raises(RuntimeError, match="successful AI call"):
        recorder.begin_tool_execution(
            ToolExecutionStart(
                turn_number=1,
                tool_ordinal=0,
                provider_tool_call_id=None,
                tool_name="lookup",
                implementation_version="v1",
                arguments={},
            )
        )

    assert tool_calls.begun == []


def test_recorder_deduplicates_identical_progress_checkpoints() -> None:
    generation_id = uuid4()
    recorder, _, _, generations = make_recorder(generation_id)

    recorder.update_progress(
        GenerationProgress(current_turn=1, current_stage="running")
    )
    recorder.update_progress(
        GenerationProgress(current_turn=1, current_stage="running")
    )
    recorder.update_progress(
        GenerationProgress(current_turn=1, current_stage="research")
    )

    assert [
        (command.generation_id, command.current_turn, command.current_stage)
        for command in generations.progress
    ] == [
        (generation_id, 1, "running"),
        (generation_id, 1, "research"),
    ]
