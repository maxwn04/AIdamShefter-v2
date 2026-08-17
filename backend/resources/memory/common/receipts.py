from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import JsonValue, model_validator

from backend.resources.memory.common.versioning import MemoryContent


class ReceiptConfidence(StrEnum):
    UNVERIFIED = "unverified"
    INFERRED = "inferred"
    SOURCE_BACKED = "source_backed"


class ReceiptedMemoryContent(MemoryContent):
    confidence: ReceiptConfidence
    primary_tool_call_id: UUID | None = None
    primary_api_request_id: UUID | None = None
    source_hints: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def validate_primary_receipt(self) -> ReceiptedMemoryContent:
        if (
            self.confidence == ReceiptConfidence.SOURCE_BACKED
            and self.primary_tool_call_id is None
            and self.primary_api_request_id is None
        ):
            raise ValueError("source-backed content requires a typed primary receipt")
        return self
