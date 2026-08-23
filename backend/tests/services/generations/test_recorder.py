"""Tests for the durable generation AI-call recorder adapter."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

from backend.resources.reporting.ai_calls import AICallManager
from backend.services.generations import GenerationExecutionRecorder
from backend.services.reporter.runner.recording import (
    ModelAttemptFinish,
    ModelAttemptStart,
    RecordedTokenUsage,
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


def test_recorder_maps_reporter_events_and_retains_success_identity() -> None:
    generation_id = uuid4()
    manager = FakeAICallManager()
    recorder = GenerationExecutionRecorder(
        generation_id,
        cast(AICallManager, manager),
    )
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
    manager = FakeAICallManager()
    recorder = GenerationExecutionRecorder(uuid4(), cast(AICallManager, manager))
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
