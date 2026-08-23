"""Immutable commands and views for durable artifact revisions."""

from __future__ import annotations

import hashlib
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from backend.resources._contracts import ContractModel


PositiveRevision = Annotated[int, Field(strict=True, ge=1, le=32767)]
PageLimit = Annotated[int, Field(strict=True, ge=1, le=200)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class AppendArtifactVersion(ContractModel):
    artifact_id: UUID
    content: str
    content_hash: Sha256Hex
    source_ai_call_id: UUID | None = None
    source_tool_call_id: UUID | None = None

    @model_validator(mode="after")
    def validate_content_hash(self) -> "AppendArtifactVersion":
        actual = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        if self.content_hash != actual:
            raise ValueError("content_hash must match the exact UTF-8 content")
        return self


class ArtifactVersionQuery(ContractModel):
    artifact_id: UUID
    limit: PageLimit = 50
    offset: NonNegativeInt = 0


class ArtifactVersion(ContractModel):
    id: UUID
    artifact_id: UUID
    generation_id: UUID
    revision_number: PositiveRevision
    content: str
    content_hash: Sha256Hex
    source_ai_call_id: UUID | None
    source_tool_call_id: UUID | None
    created_at: AwareDatetime


class ArtifactVersionSummary(ContractModel):
    id: UUID
    artifact_id: UUID
    generation_id: UUID
    revision_number: PositiveRevision
    content_hash: Sha256Hex
    source_ai_call_id: UUID | None
    source_tool_call_id: UUID | None
    created_at: AwareDatetime


class ArtifactVersionPage(ContractModel):
    items: tuple[ArtifactVersionSummary, ...]
    total: NonNegativeInt
    limit: PageLimit
    offset: NonNegativeInt


__all__ = [
    "AppendArtifactVersion",
    "ArtifactVersion",
    "ArtifactVersionPage",
    "ArtifactVersionQuery",
    "ArtifactVersionSummary",
]
