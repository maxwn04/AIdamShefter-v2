from __future__ import annotations

from typing import ClassVar, Generic, TypeVar
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from backend.resources._contracts import ContractModel, NonBlankStr
from backend.resources.memory.common.kinds import MemoryKind


class MemoryContent(ContractModel):
    memory_kind: ClassVar[MemoryKind]
    schema_version: int


class MemoryItemIdentity(ContractModel):
    item_id: UUID
    competition_id: UUID
    kind: MemoryKind
    agent_key: NonBlankStr | None = None
    created_at: AwareDatetime


class MemoryVersionMetadata(ContractModel):
    version_id: UUID
    revision_number: int = Field(gt=0, strict=True)
    content_schema_version: int = Field(gt=0, strict=True)
    introduced_revision_id: UUID
    retired_revision_id: UUID | None = None
    competition_season_id: UUID | None = None
    week: int | None = Field(default=None, ge=0, strict=True)
    occurred_at: AwareDatetime | None = None
    creating_generation_id: UUID
    creating_tool_call_id: UUID | None = None
    change_reason: NonBlankStr | None = None
    recorded_at: AwareDatetime


ContentT = TypeVar("ContentT", bound=MemoryContent)


class VersionedMemory(ContractModel, Generic[ContentT]):
    item: MemoryItemIdentity
    version: MemoryVersionMetadata
    content: ContentT

    @model_validator(mode="after")
    def validate_envelope(self) -> VersionedMemory[ContentT]:
        if self.item.kind != self.content.memory_kind:
            raise ValueError("item kind does not match content kind")
        if self.version.content_schema_version != self.content.schema_version:
            raise ValueError("version metadata does not match content schema version")
        return self
