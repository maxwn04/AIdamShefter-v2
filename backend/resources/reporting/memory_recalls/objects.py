"""Immutable commands and views for generation-start memory recall."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, Field, JsonValue

from backend.resources._contracts import ContractModel, NonBlankStr


class MemoryRecallStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class RecordGenerationMemoryRecall(ContractModel):
    generation_id: UUID
    status: MemoryRecallStatus
    result: JsonValue
    result_text: NonBlankStr
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class GenerationMemoryRecall(ContractModel):
    generation_id: UUID
    status: MemoryRecallStatus
    result: JsonValue
    result_text: str
    metadata: dict[str, JsonValue]
    created_at: AwareDatetime


__all__ = [
    "GenerationMemoryRecall",
    "MemoryRecallStatus",
    "RecordGenerationMemoryRecall",
]
