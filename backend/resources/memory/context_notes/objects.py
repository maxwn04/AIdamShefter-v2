from __future__ import annotations

from enum import StrEnum
from typing import Annotated, ClassVar, Literal
from uuid import UUID

from pydantic import Field

from backend.resources._contracts import ContractModel, NonBlankStr, Tags
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.common.versioning import MemoryContent, VersionedMemory


class ContextNoteStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class CompetitionContextNoteIdentity(ContractModel):
    scope: Literal["competition"] = "competition"
    note_key: NonBlankStr


class CompetitionSeasonContextNoteIdentity(ContractModel):
    scope: Literal["competition_season"] = "competition_season"
    competition_season_id: UUID
    note_key: NonBlankStr


class FranchiseContextNoteIdentity(ContractModel):
    scope: Literal["franchise"] = "franchise"
    franchise_id: UUID
    note_key: NonBlankStr


ContextNoteIdentity = Annotated[
    CompetitionContextNoteIdentity
    | CompetitionSeasonContextNoteIdentity
    | FranchiseContextNoteIdentity,
    Field(discriminator="scope"),
]


class ContextNoteContent(MemoryContent):
    memory_kind: ClassVar[MemoryKind] = MemoryKind.CONTEXT_NOTE
    schema_version: Literal[1] = 1
    narrative: NonBlankStr
    outlook: NonBlankStr | None = None
    status: ContextNoteStatus
    tags: Tags


class ContextNote(VersionedMemory[ContextNoteContent]):
    note_identity: ContextNoteIdentity
