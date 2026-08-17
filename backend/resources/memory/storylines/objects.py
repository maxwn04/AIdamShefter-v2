from __future__ import annotations

from enum import StrEnum
from typing import Annotated, ClassVar, Literal
from uuid import UUID

from pydantic import Field, model_validator

from backend.resources._contracts import ContractModel, NonBlankStr, Tags
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.common.references import (
    FranchiseRef,
    PlayerRef,
    SeasonRef,
    SeasonRosterRef,
    SleeperUserRef,
)
from backend.resources.memory.common.versioning import MemoryContent, VersionedMemory


class StorylineStatus(StrEnum):
    ACTIVE = "active"
    DORMANT = "dormant"
    RESOLVED = "resolved"
    ARCHIVED = "archived"


class StorylineSubjectRole(StrEnum):
    FOCUS = "focus"
    COUNTERPARTY = "counterparty"


StorylineEntityRef = Annotated[
    FranchiseRef[StorylineSubjectRole]
    | PlayerRef[StorylineSubjectRole]
    | SeasonRosterRef[StorylineSubjectRole]
    | SeasonRef[StorylineSubjectRole]
    | SleeperUserRef[StorylineSubjectRole],
    Field(discriminator="kind"),
]


class EvidenceRole(StrEnum):
    ORIGIN = "origin"
    SUPPORT = "support"
    UPDATE = "update"
    PAYOFF = "payoff"


class EvidenceReference(ContractModel):
    version_id: UUID
    role: EvidenceRole


class FactEvidenceRef(EvidenceReference):
    kind: Literal["fact"] = "fact"


class EventEvidenceRef(EvidenceReference):
    kind: Literal["event"] = "event"


EvidenceRef = Annotated[
    FactEvidenceRef | EventEvidenceRef,
    Field(discriminator="kind"),
]


class RelatedStorylineRole(StrEnum):
    RELATED_ARC = "related_arc"
    CONTINUATION = "continuation"
    COUNTERPOINT = "counterpoint"


class RelatedStorylineRef(ContractModel):
    item_id: UUID
    role: RelatedStorylineRole


class StorylineContent(MemoryContent):
    memory_kind: ClassVar[MemoryKind] = MemoryKind.STORYLINE
    schema_version: Literal[1] = 1
    headline: NonBlankStr
    summary: NonBlankStr
    status: StorylineStatus
    arc_type: NonBlankStr | None = None
    salience: int = Field(ge=1, le=5, strict=True)
    tags: Tags
    subjects: list[StorylineEntityRef]
    evidence: list[EvidenceRef]
    related_storylines: list[RelatedStorylineRef]
    callback_condition: NonBlankStr | None = None
    resolution_summary: NonBlankStr | None = None

    @model_validator(mode="after")
    def validate_relationships(self) -> StorylineContent:
        subject_ids = [(subject.kind, subject.id) for subject in self.subjects]
        if len(subject_ids) != len(set(subject_ids)):
            raise ValueError("storyline subjects must target distinct entities")
        if self.subjects and not any(
            subject.role == StorylineSubjectRole.FOCUS for subject in self.subjects
        ):
            raise ValueError("a storyline with subjects requires a focus")

        evidence_ids = [reference.version_id for reference in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("storyline evidence versions must be distinct")

        related_ids = [reference.item_id for reference in self.related_storylines]
        if len(related_ids) != len(set(related_ids)):
            raise ValueError("related storyline items must be distinct")

        return self


Storyline = VersionedMemory[StorylineContent]
