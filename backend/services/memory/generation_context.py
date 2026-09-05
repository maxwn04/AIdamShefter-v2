from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from backend.resources.memory.common.errors import (
    GenerationMemoryContextClosedError,
)
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.context_notes.objects import (
    ContextNoteContent,
    ContextNoteIdentity,
)
from backend.resources.memory.events.objects import EventContent
from backend.resources.memory.facts.objects import FactContent
from backend.resources.memory.storylines.objects import StorylineContent
from backend.resources.memory.triggers.objects import TriggerContent
from backend.services.memory.proposals import (
    MemoryMutationBundle,
    MemoryMutationMetadata,
    MemoryProposal,
    MemoryProposalContent,
    ProposedMemoryRef,
)
from backend.services.memory.retrieval_service import (
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
)


class PinnedMemoryRetrieval(Protocol):
    """Temporary boundary implemented by the retrieval service in MEMORY-11."""

    def search(
        self,
        *,
        competition_id: UUID,
        revision_id: UUID,
        request: MemoryRetrievalRequest,
    ) -> MemoryRetrievalResult: ...


class GenerationMemoryContext:
    """One generation's pinned retrieval facade and in-memory proposal buffer."""

    def __init__(
        self,
        *,
        competition_id: UUID,
        generation_id: UUID,
        pinned_revision_id: UUID,
        retrieval: PinnedMemoryRetrieval,
        competition_season_id: UUID | None = None,
        week: int | None = None,
        knowledge_cutoff_at: datetime | None = None,
        editorial_cutoff_at: datetime | None = None,
    ) -> None:
        self.competition_id = competition_id
        self.generation_id = generation_id
        self.pinned_revision_id = pinned_revision_id
        self._retrieval = retrieval
        self._competition_season_id = competition_season_id
        self._week = week
        self._knowledge_cutoff_at = knowledge_cutoff_at
        self._editorial_cutoff_at = editorial_cutoff_at
        self._proposals: list[MemoryProposal] = []
        self._closed = False

    @property
    def competition_season_id(self) -> UUID | None:
        return self._competition_season_id

    @property
    def week(self) -> int | None:
        return self._week

    @property
    def knowledge_cutoff_at(self) -> datetime | None:
        return self._knowledge_cutoff_at

    @property
    def editorial_cutoff_at(self) -> datetime | None:
        """Date eligibility boundary; observation knowledge keeps its real clock."""
        return self._editorial_cutoff_at or self._knowledge_cutoff_at

    def search(self, request: MemoryRetrievalRequest) -> MemoryRetrievalResult:
        """Search only the immutable canonical input revision."""

        self._require_open()
        return self._retrieval.search(
            competition_id=self.competition_id,
            revision_id=self.pinned_revision_id,
            request=request,
        )

    def propose_fact(
        self,
        content: FactContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> ProposedMemoryRef:
        return self._create(MemoryKind.FACT, content, metadata=metadata)

    def propose_event(
        self,
        content: EventContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> ProposedMemoryRef:
        return self._create(MemoryKind.EVENT, content, metadata=metadata)

    def propose_storyline(
        self,
        content: StorylineContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> ProposedMemoryRef:
        return self._create(MemoryKind.STORYLINE, content, metadata=metadata)

    def propose_trigger(
        self,
        content: TriggerContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> ProposedMemoryRef:
        return self._create(MemoryKind.TRIGGER, content, metadata=metadata)

    def propose_context_note(
        self,
        identity: ContextNoteIdentity,
        content: ContextNoteContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> ProposedMemoryRef:
        return self._create(
            MemoryKind.CONTEXT_NOTE,
            content,
            context_note_identity=identity,
            metadata=metadata,
        )

    def replace_fact(
        self,
        item_id: UUID,
        expected_item_revision: int,
        content: FactContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> ProposedMemoryRef:
        return self._replace(
            MemoryKind.FACT,
            item_id,
            expected_item_revision,
            content,
            metadata=metadata,
        )

    def replace_event(
        self,
        item_id: UUID,
        expected_item_revision: int,
        content: EventContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> ProposedMemoryRef:
        return self._replace(
            MemoryKind.EVENT,
            item_id,
            expected_item_revision,
            content,
            metadata=metadata,
        )

    def replace_storyline(
        self,
        item_id: UUID,
        expected_item_revision: int,
        content: StorylineContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> ProposedMemoryRef:
        return self._replace(
            MemoryKind.STORYLINE,
            item_id,
            expected_item_revision,
            content,
            metadata=metadata,
        )

    def replace_trigger(
        self,
        item_id: UUID,
        expected_item_revision: int,
        content: TriggerContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> ProposedMemoryRef:
        return self._replace(
            MemoryKind.TRIGGER,
            item_id,
            expected_item_revision,
            content,
            metadata=metadata,
        )

    def replace_context_note(
        self,
        item_id: UUID,
        expected_item_revision: int,
        content: ContextNoteContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> ProposedMemoryRef:
        return self._replace(
            MemoryKind.CONTEXT_NOTE,
            item_id,
            expected_item_revision,
            content,
            metadata=metadata,
        )

    def take_completed_bundle(self) -> MemoryMutationBundle:
        """Close the buffer and return its immutable contents exactly once."""

        self._require_open()
        bundle = MemoryMutationBundle.model_validate(
            {
                "competition_id": self.competition_id,
                "generation_id": self.generation_id,
                "expected_revision_id": self.pinned_revision_id,
                "competition_season_id": self._competition_season_id,
                "week": self._week,
                "knowledge_cutoff_at": self._knowledge_cutoff_at,
                "proposals": tuple(self._proposals),
            }
        )
        self._closed = True
        return bundle

    def proposal_snapshot(self) -> tuple[MemoryProposal, ...]:
        """Return the currently buffered proposals without closing the context."""

        self._require_open()
        return tuple(self._proposals)

    @contextmanager
    def proposal_savepoint(self) -> Iterator[None]:
        """Discard this tool's buffered changes if any dependent write fails."""

        self._require_open()
        start = len(self._proposals)
        try:
            yield
        except BaseException:
            del self._proposals[start:]
            raise

    def discard(self) -> None:
        """Close and erase an abandoned proposal buffer without persistence."""

        if self._closed:
            return
        self._proposals.clear()
        self._closed = True

    def _create(
        self,
        kind: MemoryKind,
        content: MemoryProposalContent,
        *,
        context_note_identity: ContextNoteIdentity | None = None,
        metadata: MemoryMutationMetadata | None = None,
    ) -> ProposedMemoryRef:
        self._require_open()
        proposal = MemoryProposal(
            proposal_id=uuid4(),
            operation="create",
            kind=kind,
            item_id=uuid4(),
            version_id=uuid4(),
            content=content,
            context_note_identity=context_note_identity,
            metadata=metadata or MemoryMutationMetadata(),
        )
        self._proposals.append(proposal)
        return proposal.proposed_ref()

    def _replace(
        self,
        kind: MemoryKind,
        item_id: UUID,
        expected_item_revision: int,
        content: MemoryProposalContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> ProposedMemoryRef:
        self._require_open()
        proposal = MemoryProposal(
            proposal_id=uuid4(),
            operation="replace",
            kind=kind,
            item_id=item_id,
            version_id=uuid4(),
            expected_item_revision=expected_item_revision,
            content=content,
            metadata=metadata or MemoryMutationMetadata(),
        )
        self._proposals.append(proposal)
        return proposal.proposed_ref()

    def _require_open(self) -> None:
        if self._closed:
            raise GenerationMemoryContextClosedError(self.generation_id)
