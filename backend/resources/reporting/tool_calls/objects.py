"""Immutable commands and views for durable reporter tool executions."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, JsonValue, model_validator

from backend.resources._contracts import ContractModel, NonBlankStr


NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PageLimit = Annotated[int, Field(strict=True, ge=1, le=200)]


class ToolCallStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ToolCallTerminalStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BeginToolCall(ContractModel):
    generation_id: UUID
    ai_call_id: UUID
    tool_ordinal: NonNegativeInt
    provider_tool_call_id: NonBlankStr | None = None
    tool_name: NonBlankStr
    implementation_version: NonBlankStr
    arguments: dict[str, JsonValue]


class FinishToolCall(ContractModel):
    tool_call_id: UUID
    status: ToolCallTerminalStatus
    full_result_text: str | None = None
    structured_result: dict[str, JsonValue] | list[JsonValue] | None = None
    error_text: NonBlankStr | None = None
    error: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> "FinishToolCall":
        if self.status in {
            ToolCallTerminalStatus.SUCCEEDED,
            ToolCallTerminalStatus.FAILED,
        } and self.full_result_text is None:
            raise ValueError("completed tool calls require the full result text")
        if self.status is ToolCallTerminalStatus.SUCCEEDED and (
            self.error_text is not None or self.error is not None
        ):
            raise ValueError("a successful tool call cannot include an error")
        return self


class ToolCallQuery(ContractModel):
    generation_id: UUID
    ai_call_id: UUID | None = None
    status: ToolCallStatus | None = None
    limit: PageLimit = 50
    offset: NonNegativeInt = 0


class ToolCall(ContractModel):
    id: UUID
    generation_id: UUID
    ai_call_id: UUID
    tool_ordinal: int
    provider_tool_call_id: str | None
    tool_name: str
    implementation_version: str
    arguments: dict[str, JsonValue]
    status: ToolCallStatus
    full_result_text: str | None
    structured_result: dict[str, JsonValue] | list[JsonValue] | None
    error_text: str | None
    error: dict[str, JsonValue] | None
    started_at: AwareDatetime
    completed_at: AwareDatetime | None
    duration_ms: int | None


class ToolCallSummary(ContractModel):
    id: UUID
    generation_id: UUID
    ai_call_id: UUID
    tool_ordinal: int
    provider_tool_call_id: str | None
    tool_name: str
    implementation_version: str
    status: ToolCallStatus
    started_at: AwareDatetime
    completed_at: AwareDatetime | None
    duration_ms: int | None


class ToolCallPage(ContractModel):
    items: tuple[ToolCallSummary, ...]
    total: NonNegativeInt
    limit: PageLimit
    offset: NonNegativeInt


__all__ = [
    "BeginToolCall",
    "FinishToolCall",
    "ToolCall",
    "ToolCallPage",
    "ToolCallQuery",
    "ToolCallStatus",
    "ToolCallSummary",
    "ToolCallTerminalStatus",
]
