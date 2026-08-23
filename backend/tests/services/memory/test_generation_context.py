from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from backend.resources.memory.common.errors import GenerationMemoryContextClosedError
from backend.resources.memory.events.objects import EventContent
from backend.resources.memory.facts.objects import FactContent
from backend.resources.memory.search_documents import SearchDocumentQuery
from backend.services.memory import (
    GenerationMemoryContext,
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
)


class RecordingRetrieval:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, UUID, MemoryRetrievalRequest]] = []

    def search(
        self,
        *,
        competition_id: UUID,
        revision_id: UUID,
        request: MemoryRetrievalRequest,
    ) -> MemoryRetrievalResult:
        self.calls.append((competition_id, revision_id, request))
        return MemoryRetrievalResult(
            competition_id=competition_id,
            revision_id=revision_id,
            matches=(),
        )


def _event() -> EventContent:
    return EventContent.model_validate(
        {
            "event_type": "matchup",
            "headline": "A rivalry game changed the table.",
            "summary": "The favorite lost a close matchup.",
            "salience": 4,
            "confidence": "inferred",
            "status": "active",
            "details": {
                "kind": "matchup",
                "winner_franchise_id": uuid4(),
                "loser_franchise_id": uuid4(),
                "sleeper_matchup_id": "week-7-a",
            },
        }
    )


def _fact(event_version_id: UUID) -> FactContent:
    return FactContent.model_validate(
        {
            "claim": "The underdog won the rivalry game.",
            "category": "result",
            "numbers": {"wins": 1},
            "confidence": "inferred",
            "status": "active",
            "subjects": [],
            "originating_event_version_ids": [event_version_id],
        }
    )


def test_context_keeps_search_pinned_and_finalizes_its_buffer_once() -> None:
    competition_id = uuid4()
    generation_id = uuid4()
    revision_id = uuid4()
    retrieval = RecordingRetrieval()
    context = GenerationMemoryContext(
        competition_id=competition_id,
        generation_id=generation_id,
        pinned_revision_id=revision_id,
        retrieval=retrieval,
    )

    event_ref = context.propose_event(_event())
    fact_ref = context.propose_fact(_fact(event_ref.version_id))
    request = MemoryRetrievalRequest(query=SearchDocumentQuery(text="rivalry"))
    result = context.search(request)
    assert result.competition_id == competition_id
    assert result.revision_id == revision_id
    assert result.matches == ()
    assert retrieval.calls == [
        (competition_id, revision_id, request)
    ]

    bundle = context.take_completed_bundle()
    assert [proposal.proposed_ref() for proposal in bundle.proposals] == [
        event_ref,
        fact_ref,
    ]
    fact_content = bundle.proposals[1].content
    assert isinstance(fact_content, FactContent)
    assert fact_content.originating_event_version_ids == [
        event_ref.version_id
    ]
    with pytest.raises(GenerationMemoryContextClosedError):
        context.take_completed_bundle()
    with pytest.raises(GenerationMemoryContextClosedError):
        context.search(
            MemoryRetrievalRequest(
                query=SearchDocumentQuery(text="buffered fact")
            )
        )


def test_discard_closes_an_abandoned_proposal_buffer() -> None:
    context = GenerationMemoryContext(
        competition_id=uuid4(),
        generation_id=uuid4(),
        pinned_revision_id=uuid4(),
        retrieval=RecordingRetrieval(),
    )
    context.propose_event(_event())

    context.discard()
    context.discard()

    with pytest.raises(GenerationMemoryContextClosedError):
        context.take_completed_bundle()
