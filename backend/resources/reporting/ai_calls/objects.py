"""Immutable commands and views for durable model-provider attempts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, JsonValue, model_validator

from backend.resources._contracts import ContractModel, NonBlankStr


PositiveInt = Annotated[int, Field(strict=True, ge=1)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PageLimit = Annotated[int, Field(strict=True, ge=1, le=200)]


class AICallStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    RETRYABLE_ERROR = "retryable_error"
    FATAL_ERROR = "fatal_error"
    CANCELLED = "cancelled"
    UNKNOWN_OUTCOME = "unknown_outcome"


class AICallTerminalStatus(StrEnum):
    SUCCEEDED = "succeeded"
    RETRYABLE_ERROR = "retryable_error"
    FATAL_ERROR = "fatal_error"
    CANCELLED = "cancelled"
    UNKNOWN_OUTCOME = "unknown_outcome"


class TokenUsage(ContractModel):
    input_tokens: NonNegativeInt | None = None
    cached_input_tokens: NonNegativeInt | None = None
    output_tokens: NonNegativeInt | None = None
    reasoning_tokens: NonNegativeInt | None = None
    total_tokens: NonNegativeInt | None = None
    raw_provider_usage: dict[str, JsonValue] | None = None


class BeginAICall(ContractModel):
    generation_id: UUID
    turn_number: PositiveInt
    requested_provider: NonBlankStr | None = None
    requested_model: NonBlankStr
    input_messages: tuple[dict[str, JsonValue], ...]
    tool_definitions: tuple[dict[str, JsonValue], ...]
    request_parameters: dict[str, JsonValue]


class FinishAICall(ContractModel):
    ai_call_id: UUID
    status: AICallTerminalStatus
    actual_provider: NonBlankStr | None = None
    actual_model: NonBlankStr | None = None
    provider_response: dict[str, JsonValue] | None = None
    error: dict[str, JsonValue] | None = None
    finish_reason: NonBlankStr | None = None
    provider_request_id: NonBlankStr | None = None
    provider_response_id: NonBlankStr | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)

    @model_validator(mode="after")
    def validate_success(self) -> "FinishAICall":
        if self.status is AICallTerminalStatus.SUCCEEDED:
            if self.actual_model is None or self.provider_response is None:
                raise ValueError(
                    "a successful AI call requires actual_model and provider_response"
                )
            if self.error is not None:
                raise ValueError("a successful AI call cannot include an error")
        return self


class AICallQuery(ContractModel):
    generation_id: UUID
    turn_number: PositiveInt | None = None
    status: AICallStatus | None = None
    limit: PageLimit = 50
    offset: NonNegativeInt = 0


class AICall(ContractModel):
    id: UUID
    generation_id: UUID
    turn_number: int
    attempt_number: int
    requested_provider: str | None
    requested_model: str
    actual_provider: str | None
    actual_model: str | None
    input_messages: tuple[dict[str, JsonValue], ...]
    tool_definitions: tuple[dict[str, JsonValue], ...]
    request_parameters: dict[str, JsonValue]
    provider_response: dict[str, JsonValue] | None
    status: AICallStatus
    error: dict[str, JsonValue] | None
    finish_reason: str | None
    provider_request_id: str | None
    provider_response_id: str | None
    usage: TokenUsage
    started_at: AwareDatetime
    completed_at: AwareDatetime | None
    latency_ms: int | None


class AICallSummary(ContractModel):
    id: UUID
    generation_id: UUID
    turn_number: int
    attempt_number: int
    requested_provider: str | None
    requested_model: str
    actual_provider: str | None
    actual_model: str | None
    status: AICallStatus
    finish_reason: str | None
    usage: TokenUsage
    started_at: AwareDatetime
    completed_at: AwareDatetime | None
    latency_ms: int | None


class AICallPage(ContractModel):
    items: tuple[AICallSummary, ...]
    total: NonNegativeInt
    limit: PageLimit
    offset: NonNegativeInt


__all__ = [
    "AICall",
    "AICallPage",
    "AICallQuery",
    "AICallStatus",
    "AICallSummary",
    "AICallTerminalStatus",
    "BeginAICall",
    "FinishAICall",
    "TokenUsage",
]
