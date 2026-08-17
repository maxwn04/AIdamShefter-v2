from __future__ import annotations

from collections.abc import Iterable
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from backend.resources._contracts import ContractModel, NonBlankStr
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.context_notes.objects import (
    ContextNoteContent,
    ContextNoteIdentity,
)
from backend.resources.memory.events.objects import EventContent
from backend.resources.memory.facts.objects import FactContent
from backend.resources.memory.revisions.objects import CanonicalRevision
from backend.resources.memory.storylines.objects import StorylineContent
from backend.resources.memory.triggers.objects import TriggerContent


MemoryProposalContent = (
    FactContent
    | EventContent
    | StorylineContent
    | TriggerContent
    | ContextNoteContent
)


class MemoryMutationMetadata(ContractModel):
    """Version-envelope values supplied with one complete proposal."""

    agent_key: NonBlankStr | None = None
    competition_season_id: UUID | None = None
    week: int | None = Field(default=None, ge=0, strict=True)
    occurred_at: AwareDatetime | None = None
    creating_tool_call_id: UUID | None = None
    change_reason: NonBlankStr | None = None


class ProposedMemoryRef(ContractModel):
    """Preallocated canonical identity returned to a proposal caller."""

    proposal_id: UUID
    kind: MemoryKind
    item_id: UUID
    version_id: UUID


class MemoryProposal(ContractModel):
    """One complete create or replacement inside an atomic bundle."""

    proposal_id: UUID
    operation: Literal["create", "replace"]
    kind: MemoryKind
    item_id: UUID
    version_id: UUID
    expected_item_revision: int | None = Field(default=None, gt=0, strict=True)
    content: MemoryProposalContent
    context_note_identity: ContextNoteIdentity | None = None
    metadata: MemoryMutationMetadata = MemoryMutationMetadata()

    @model_validator(mode="after")
    def validate_shape(self) -> MemoryProposal:
        if self.content.memory_kind is not self.kind:
            raise ValueError("proposal kind does not match its typed content")
        if self.operation == "create" and self.expected_item_revision is not None:
            raise ValueError("create proposal cannot expect an item revision")
        if self.operation == "replace" and self.expected_item_revision is None:
            raise ValueError("replacement proposal requires an expected item revision")
        has_note_identity = self.context_note_identity is not None
        if has_note_identity != (
            self.operation == "create" and self.kind is MemoryKind.CONTEXT_NOTE
        ):
            raise ValueError(
                "context-note identity is required exactly for context-note creates"
            )
        if self.operation == "replace" and self.metadata.agent_key is not None:
            raise ValueError("replacement proposal cannot change an agent key")
        return self

    def proposed_ref(self) -> ProposedMemoryRef:
        return ProposedMemoryRef(
            proposal_id=self.proposal_id,
            kind=self.kind,
            item_id=self.item_id,
            version_id=self.version_id,
        )


class MemoryMutationBundle(ContractModel):
    """The immutable, generation-completed canonical mutation unit."""

    competition_id: UUID
    generation_id: UUID
    expected_revision_id: UUID
    competition_season_id: UUID | None = None
    week: int | None = Field(default=None, ge=0, strict=True)
    knowledge_cutoff_at: AwareDatetime | None = None
    proposals: tuple[MemoryProposal, ...]

    @model_validator(mode="after")
    def validate_distinct_proposals(self) -> MemoryMutationBundle:
        _require_unique(
            (proposal.proposal_id for proposal in self.proposals),
            "proposal IDs",
        )
        _require_unique(
            (proposal.version_id for proposal in self.proposals),
            "proposed version IDs",
        )
        _require_unique(
            (proposal.item_id for proposal in self.proposals),
            "proposed item targets",
        )
        return self


class MemoryMutationOrigin(ContractModel):
    """Canonical parent and reporting provenance for a public mutation."""

    generation_id: UUID
    expected_revision_id: UUID
    competition_season_id: UUID | None = None
    week: int | None = Field(default=None, ge=0, strict=True)
    knowledge_cutoff_at: AwareDatetime | None = None


class MemoryMutationResult(ContractModel):
    """Committed revision and the canonical identities introduced within it."""

    revision: CanonicalRevision | None
    changes: tuple[ProposedMemoryRef, ...]


def _require_unique(values: Iterable[UUID], label: str) -> None:
    materialized = tuple(values)
    if len(materialized) != len(set(materialized)):
        raise ValueError(f"{label} must be distinct within a mutation bundle")
