"""Reporter-facing contracts for generation-scoped completion recording."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol
from uuid import UUID

from pydantic import JsonValue


ModelAttemptStatus = Literal[
    "succeeded",
    "retryable_error",
    "fatal_error",
    "cancelled",
    "unknown_outcome",
]
ToolExecutionStatus = Literal["succeeded", "failed", "cancelled"]


class ArtifactRecordingError(RuntimeError):
    """Durable artifact recording failed, so reporter execution must stop."""


@dataclass(frozen=True, slots=True)
class RecordedTokenUsage:
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    raw_provider_usage: dict[str, JsonValue] | None = None


@dataclass(frozen=True, slots=True)
class ModelAttemptStart:
    turn_number: int
    requested_provider: str | None
    requested_model: str
    input_messages: tuple[dict[str, JsonValue], ...]
    tool_definitions: tuple[dict[str, JsonValue], ...]
    request_parameters: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ModelAttemptFinish:
    status: ModelAttemptStatus
    actual_provider: str | None = None
    actual_model: str | None = None
    provider_response: dict[str, JsonValue] | None = None
    error: dict[str, JsonValue] | None = None
    finish_reason: str | None = None
    provider_request_id: str | None = None
    provider_response_id: str | None = None
    usage: RecordedTokenUsage = field(default_factory=RecordedTokenUsage)


@dataclass(frozen=True, slots=True)
class ToolExecutionStart:
    turn_number: int
    tool_ordinal: int
    provider_tool_call_id: str | None
    tool_name: str
    implementation_version: str
    arguments: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ToolExecutionFinish:
    status: ToolExecutionStatus
    full_result_text: str | None = None
    structured_result: dict[str, JsonValue] | list[JsonValue] | None = None
    error_text: str | None = None
    error: dict[str, JsonValue] | None = None


@dataclass(frozen=True, slots=True)
class ArtifactMutation:
    path: str
    media_type: Literal["text/markdown"]
    content: str
    revision: int
    content_hash: str
    source_tool_call_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class GenerationProgress:
    current_turn: int
    current_stage: str


class CompletionRecorder(Protocol):
    """Record provider attempts for exactly one durable generation."""

    def begin_model_attempt(self, attempt: ModelAttemptStart) -> UUID: ...

    def finish_model_attempt(
        self,
        attempt_id: UUID,
        result: ModelAttemptFinish,
    ) -> None: ...

    def successful_ai_call_id(self, turn_number: int) -> UUID | None: ...


class RunnerRecorder(Protocol):
    """Record tool execution and bounded progress for one reporter run."""

    def begin_tool_execution(self, execution: ToolExecutionStart) -> UUID: ...

    def finish_tool_execution(
        self,
        execution_id: UUID,
        result: ToolExecutionFinish,
    ) -> None: ...

    def update_progress(self, progress: GenerationProgress) -> None: ...


class ArtifactRecorder(Protocol):
    """Record complete immutable snapshots for one generation."""

    def record_artifact_mutation(
        self,
        mutation: ArtifactMutation,
    ) -> UUID | None: ...


class ExecutionRecorder(
    CompletionRecorder,
    RunnerRecorder,
    ArtifactRecorder,
    Protocol,
):
    """Complete durable recorder contract used by a generation run."""


__all__ = [
    "ArtifactMutation",
    "ArtifactRecorder",
    "ArtifactRecordingError",
    "CompletionRecorder",
    "ExecutionRecorder",
    "GenerationProgress",
    "ModelAttemptFinish",
    "ModelAttemptStart",
    "ModelAttemptStatus",
    "RecordedTokenUsage",
    "RunnerRecorder",
    "ToolExecutionFinish",
    "ToolExecutionStart",
    "ToolExecutionStatus",
]
