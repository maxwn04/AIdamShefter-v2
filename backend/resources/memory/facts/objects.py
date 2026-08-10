from __future__ import annotations

from enum import StrEnum
from typing import Annotated, ClassVar, Literal
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from backend.resources._contracts import NonBlankStr
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.common.receipts import (
    ReceiptConfidence,
    ReceiptedMemoryContent,
)
from backend.resources.memory.common.references import (
    FranchiseRef,
    PlayerRef,
    SeasonRef,
    SeasonRosterRef,
    SleeperUserRef,
)
from backend.resources.memory.common.versioning import VersionedMemory


FactConfidence = ReceiptConfidence


class FactStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class FactSubjectRole(StrEnum):
    SUBJECT = "subject"


FactEntityRef = Annotated[
    FranchiseRef[FactSubjectRole]
    | PlayerRef[FactSubjectRole]
    | SeasonRosterRef[FactSubjectRole]
    | SeasonRef[FactSubjectRole]
    | SleeperUserRef[FactSubjectRole],
    Field(discriminator="kind"),
]


class FactContent(ReceiptedMemoryContent):
    memory_kind: ClassVar[MemoryKind] = MemoryKind.FACT
    schema_version: Literal[1] = 1
    claim: NonBlankStr
    category: NonBlankStr
    numbers: dict[str, JsonValue]
    status: FactStatus
    subjects: list[FactEntityRef]
    originating_event_version_ids: list[UUID]

    @model_validator(mode="after")
    def validate_evidence(self) -> FactContent:
        subject_ids = [(subject.kind, subject.id) for subject in self.subjects]
        if len(subject_ids) != len(set(subject_ids)):
            raise ValueError("fact subjects must target distinct entities")

        if len(self.originating_event_version_ids) != len(
            set(self.originating_event_version_ids)
        ):
            raise ValueError("originating event versions must be distinct")

        return self


Fact = VersionedMemory[FactContent]
