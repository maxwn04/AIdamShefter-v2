from __future__ import annotations

from uuid import UUID, uuid4

from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.context_notes.codec import stored_context_note_content
from backend.resources.memory.context_notes.objects import (
    ContextNoteContent,
    ContextNoteIdentity,
)
from backend.resources.memory.context_notes.shared import (
    context_note_persister,
)
from backend.resources.memory.events.codec import stored_event_content
from backend.resources.memory.events.objects import EventContent
from backend.resources.memory.events.shared import event_persister
from backend.resources.memory.facts.codec import stored_fact_content
from backend.resources.memory.facts.objects import FactContent
from backend.resources.memory.facts.shared import fact_persister
from backend.resources.memory.revisions.manager import RevisionManager
from backend.resources.memory.revisions.writers import (
    CanonicalReferenceTarget,
    CanonicalResourceWrite,
    CanonicalWriteBundle,
)
from backend.resources.memory.storylines.codec import stored_storyline_content
from backend.resources.memory.storylines.objects import StorylineContent
from backend.resources.memory.storylines.shared import (
    storyline_persister,
)
from backend.resources.memory.triggers.codec import stored_trigger_content
from backend.resources.memory.triggers.objects import TriggerContent
from backend.resources.memory.triggers.shared import (
    trigger_persister,
)
from backend.services.memory.proposals import (
    MemoryMutationBundle,
    MemoryMutationMetadata,
    MemoryMutationOrigin,
    MemoryMutationResult,
    MemoryProposal,
    MemoryProposalContent,
)


_WRITE_ORDER = {
    MemoryKind.EVENT: 0,
    MemoryKind.FACT: 1,
    MemoryKind.STORYLINE: 2,
    MemoryKind.TRIGGER: 3,
    MemoryKind.CONTEXT_NOTE: 4,
}


class MemoryMutationService:
    """Translate complete public proposals into one canonical revision commit."""

    def __init__(self, revision_manager: RevisionManager) -> None:
        self._revision_manager = revision_manager

    def apply(self, bundle: MemoryMutationBundle) -> MemoryMutationResult:
        """Apply a completed generation bundle exactly as one mutation unit."""

        writes = tuple(_canonical_write(proposal) for proposal in bundle.proposals)
        revision = self._revision_manager.commit(
            CanonicalWriteBundle(
                competition_id=bundle.competition_id,
                generation_id=bundle.generation_id,
                expected_revision_id=bundle.expected_revision_id,
                competition_season_id=bundle.competition_season_id,
                week=bundle.week,
                knowledge_cutoff_at=bundle.knowledge_cutoff_at,
                writes=writes,
            )
        )
        return MemoryMutationResult(
            revision=revision,
            changes=tuple(
                proposal.proposed_ref() for proposal in bundle.proposals
            ),
        )

    def create_fact(
        self,
        origin: MemoryMutationOrigin,
        content: FactContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> MemoryMutationResult:
        return self._single_create(origin, MemoryKind.FACT, content, metadata=metadata)

    def replace_fact(
        self,
        origin: MemoryMutationOrigin,
        item_id: UUID,
        expected_item_revision: int,
        content: FactContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> MemoryMutationResult:
        return self._single_replace(
            origin,
            MemoryKind.FACT,
            item_id,
            expected_item_revision,
            content,
            metadata=metadata,
        )

    def create_event(
        self,
        origin: MemoryMutationOrigin,
        content: EventContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> MemoryMutationResult:
        return self._single_create(origin, MemoryKind.EVENT, content, metadata=metadata)

    def replace_event(
        self,
        origin: MemoryMutationOrigin,
        item_id: UUID,
        expected_item_revision: int,
        content: EventContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> MemoryMutationResult:
        return self._single_replace(
            origin,
            MemoryKind.EVENT,
            item_id,
            expected_item_revision,
            content,
            metadata=metadata,
        )

    def create_storyline(
        self,
        origin: MemoryMutationOrigin,
        content: StorylineContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> MemoryMutationResult:
        return self._single_create(
            origin,
            MemoryKind.STORYLINE,
            content,
            metadata=metadata,
        )

    def replace_storyline(
        self,
        origin: MemoryMutationOrigin,
        item_id: UUID,
        expected_item_revision: int,
        content: StorylineContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> MemoryMutationResult:
        return self._single_replace(
            origin,
            MemoryKind.STORYLINE,
            item_id,
            expected_item_revision,
            content,
            metadata=metadata,
        )

    def create_trigger(
        self,
        origin: MemoryMutationOrigin,
        content: TriggerContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> MemoryMutationResult:
        return self._single_create(
            origin,
            MemoryKind.TRIGGER,
            content,
            metadata=metadata,
        )

    def replace_trigger(
        self,
        origin: MemoryMutationOrigin,
        item_id: UUID,
        expected_item_revision: int,
        content: TriggerContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> MemoryMutationResult:
        return self._single_replace(
            origin,
            MemoryKind.TRIGGER,
            item_id,
            expected_item_revision,
            content,
            metadata=metadata,
        )

    def create_context_note(
        self,
        origin: MemoryMutationOrigin,
        identity: ContextNoteIdentity,
        content: ContextNoteContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> MemoryMutationResult:
        return self._single_create(
            origin,
            MemoryKind.CONTEXT_NOTE,
            content,
            context_note_identity=identity,
            metadata=metadata,
        )

    def replace_context_note(
        self,
        origin: MemoryMutationOrigin,
        item_id: UUID,
        expected_item_revision: int,
        content: ContextNoteContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> MemoryMutationResult:
        return self._single_replace(
            origin,
            MemoryKind.CONTEXT_NOTE,
            item_id,
            expected_item_revision,
            content,
            metadata=metadata,
        )

    def _single_create(
        self,
        origin: MemoryMutationOrigin,
        kind: MemoryKind,
        content: MemoryProposalContent,
        *,
        context_note_identity: ContextNoteIdentity | None = None,
        metadata: MemoryMutationMetadata | None = None,
    ) -> MemoryMutationResult:
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
        return self.apply(_single_bundle(self._revision_manager, origin, proposal))

    def _single_replace(
        self,
        origin: MemoryMutationOrigin,
        kind: MemoryKind,
        item_id: UUID,
        expected_item_revision: int,
        content: MemoryProposalContent,
        *,
        metadata: MemoryMutationMetadata | None = None,
    ) -> MemoryMutationResult:
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
        return self.apply(_single_bundle(self._revision_manager, origin, proposal))


def _single_bundle(
    revision_manager: RevisionManager,
    origin: MemoryMutationOrigin,
    proposal: MemoryProposal,
) -> MemoryMutationBundle:
    return MemoryMutationBundle(
        competition_id=revision_manager.competition_id,
        generation_id=origin.generation_id,
        expected_revision_id=origin.expected_revision_id,
        competition_season_id=origin.competition_season_id,
        week=origin.week,
        knowledge_cutoff_at=origin.knowledge_cutoff_at,
        proposals=(proposal,),
    )


def _canonical_write(proposal: MemoryProposal) -> CanonicalResourceWrite:
    content = proposal.content
    if isinstance(content, FactContent):
        persist = fact_persister(content)
        stored_content = stored_fact_content(content)
    elif isinstance(content, EventContent):
        persist = event_persister(content)
        stored_content = stored_event_content(content)
    elif isinstance(content, StorylineContent):
        persist = storyline_persister(content)
        stored_content = stored_storyline_content(content)
    elif isinstance(content, TriggerContent):
        persist = trigger_persister(content)
        stored_content = stored_trigger_content(content)
    elif isinstance(content, ContextNoteContent):
        persist = context_note_persister(
            proposal.operation,
            proposal.context_note_identity,
            content,
        )
        stored_content = stored_context_note_content(content)
    else:
        raise TypeError(f"unsupported memory content {type(content).__name__}")

    metadata = proposal.metadata
    return CanonicalResourceWrite(
        operation=proposal.operation,
        kind=proposal.kind,
        dependency_order=_WRITE_ORDER[proposal.kind],
        item_id=proposal.item_id,
        version_id=proposal.version_id,
        expected_item_revision=proposal.expected_item_revision,
        content_schema_version=content.schema_version,
        agent_key=metadata.agent_key,
        competition_season_id=metadata.competition_season_id,
        week=metadata.week,
        occurred_at=metadata.occurred_at,
        creating_tool_call_id=metadata.creating_tool_call_id,
        change_reason=metadata.change_reason,
        stored_content=stored_content,
        context_note_identity=proposal.context_note_identity,
        references=_references(content),
        persist_typed=persist,
    )


def _references(
    content: MemoryProposalContent,
) -> tuple[CanonicalReferenceTarget, ...]:
    references: list[CanonicalReferenceTarget] = []
    if isinstance(content, FactContent):
        references.extend(
            CanonicalReferenceTarget(
                reference_id=version_id,
                target="version",
                expected_kinds=(MemoryKind.EVENT,),
            )
            for version_id in content.originating_event_version_ids
        )
    elif isinstance(content, StorylineContent):
        references.extend(
            CanonicalReferenceTarget(
                reference_id=evidence.version_id,
                target="version",
                expected_kinds=(MemoryKind(evidence.kind),),
            )
            for evidence in content.evidence
        )
        references.extend(
            CanonicalReferenceTarget(
                reference_id=related.item_id,
                target="item",
                expected_kinds=(MemoryKind.STORYLINE,),
            )
            for related in content.related_storylines
        )
    elif isinstance(content, TriggerContent):
        if content.target_storyline_item_id is not None:
            references.append(
                CanonicalReferenceTarget(
                    reference_id=content.target_storyline_item_id,
                    target="item",
                    expected_kinds=(MemoryKind.STORYLINE,),
                )
            )
        if content.origin_event_item_id is not None:
            references.append(
                CanonicalReferenceTarget(
                    reference_id=content.origin_event_item_id,
                    target="item",
                    expected_kinds=(MemoryKind.EVENT,),
                )
            )
    return tuple(references)
