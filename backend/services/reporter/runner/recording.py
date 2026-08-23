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


class CompletionRecorder(Protocol):
    """Record provider attempts for exactly one durable generation."""

    def begin_model_attempt(self, attempt: ModelAttemptStart) -> UUID: ...

    def finish_model_attempt(
        self,
        attempt_id: UUID,
        result: ModelAttemptFinish,
    ) -> None: ...

    def successful_ai_call_id(self, turn_number: int) -> UUID | None: ...


__all__ = [
    "CompletionRecorder",
    "ModelAttemptFinish",
    "ModelAttemptStart",
    "ModelAttemptStatus",
    "RecordedTokenUsage",
]
