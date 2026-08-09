from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest

from backend.resources.memory.errors import SearchProjectionUnavailable
from backend.resources.memory.objects import (
    ExpansionPolicy,
    FactContent,
    FactConfidence,
    FactStatus,
    FranchiseKey,
    HydratedMemoryVersion,
    MemoryKind,
    MemoryQuery,
    MemoryRevisionRef,
    TypedMemoryVersion,
)
from backend.resources.memory.search_documents import entity_search_key
from backend.services.memory.service import MemoryService


REVISION = MemoryRevisionRef(
    id=UUID("00000000-0000-0000-0000-000000000010"),
    competition_id=UUID("00000000-0000-0000-0000-000000000020"),
    sequence_number=3,
    state_content_hash="revision-three",
)


@dataclass(frozen=True)
class Candidate:
    version_id: UUID
    lexical_match: bool = False
    matched_entities: tuple[str, ...] = ()
    matched_evidence_version_ids: tuple[UUID, ...] = ()
    matched_related_item_ids: tuple[UUID, ...] = ()
    salience: int | None = None
    recorded_at: datetime = datetime(2026, 8, 9, tzinfo=UTC)


def _memory(version_id: UUID) -> HydratedMemoryVersion:
    return HydratedMemoryVersion(
        version=TypedMemoryVersion(
            version_id=version_id,
            item_id=UUID(int=version_id.int + 100),
            competition_id=REVISION.competition_id,
            kind=MemoryKind.FACT,
            revision_number=1,
            content_schema_version=1,
            introduced_revision_id=REVISION.id,
            creating_generation_id=UUID(int=version_id.int + 200),
            recorded_at=datetime(2026, 8, 9, tzinfo=UTC),
            content=FactContent(
                claim="The Sharks have won three straight.",
                category="streak",
                confidence=FactConfidence.INFERRED,
                status=FactStatus.ACTIVE,
            ),
        )
    )


class RetrievalManager:
    def __init__(
        self,
        primary: tuple[Candidate, ...],
        fallback: tuple[Candidate, ...] = (),
        *,
        projection_available: bool = True,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.projection_available = projection_available
        self.find_revisions: list[MemoryRevisionRef] = []
        self.scan_revisions: list[MemoryRevisionRef] = []
        all_candidates = {candidate.version_id for candidate in primary + fallback}
        self.memories = {version_id: _memory(version_id) for version_id in all_candidates}

    def get_revision(self, revision_id, competition_id=None):
        assert revision_id == REVISION.id
        assert competition_id is None
        return REVISION

    def find_candidates(self, revision, query):
        self.find_revisions.append(revision)
        if not self.projection_available:
            raise SearchProjectionUnavailable
        return self.primary

    def scan_visible_candidates(self, revision, query):
        self.scan_revisions.append(revision)
        return self.fallback

    def hydrate_visible_versions(self, revision, version_ids, expansion):
        assert revision is REVISION
        return {version_id: self.memories[version_id] for version_id in version_ids}


def test_service_applies_deterministic_policy_to_raw_signals() -> None:
    lexical_id = UUID("00000000-0000-0000-0000-000000000001")
    exact_id = UUID("00000000-0000-0000-0000-000000000002")
    evidence_id = UUID("00000000-0000-0000-0000-000000000003")
    franchise = FranchiseKey(id=UUID("00000000-0000-0000-0000-000000000004"))
    manager = RetrievalManager(
        (
            Candidate(
                lexical_id,
                lexical_match=True,
                matched_entities=(entity_search_key(franchise),),
            ),
            Candidate(
                exact_id,
                matched_evidence_version_ids=(evidence_id,),
                recorded_at=datetime(2025, 8, 9, tzinfo=UTC),
            ),
        )
    )

    result = MemoryService(manager).at_revision(REVISION.id).retrieve(
        MemoryQuery(entities=(franchise,), evidence_version_ids={evidence_id})
    )

    assert [entry.memory.version.version_id for entry in result.entries] == [
        exact_id,
        lexical_id,
    ]
    assert result.entries[0].match_reasons == ("exact_evidence",)
    assert result.entries[1].matched_entities == (franchise,)
    assert not hasattr(result.entries[0], "rank_components")


def test_fallback_ranks_its_full_bounded_pool_before_applying_result_limit() -> None:
    weaker_id = UUID("00000000-0000-0000-0000-000000000001")
    stronger_id = UUID("00000000-0000-0000-0000-000000000002")
    evidence_id = UUID("00000000-0000-0000-0000-000000000003")
    manager = RetrievalManager(
        (),
        (
            Candidate(weaker_id, lexical_match=True),
            Candidate(
                stronger_id,
                matched_evidence_version_ids=(evidence_id,),
            ),
        ),
        projection_available=False,
    )

    result = MemoryService(manager).at_revision(REVISION.id).retrieve(
        MemoryQuery(evidence_version_ids={evidence_id}, limit=1)
    )

    assert result.degraded is True
    assert result.entries[0].memory.version.version_id == stronger_id
    assert manager.scan_revisions == [REVISION]


def test_primary_and_fallback_paths_report_the_same_stable_reasons() -> None:
    version_id = UUID("00000000-0000-0000-0000-000000000001")
    related_item_id = UUID("00000000-0000-0000-0000-000000000002")
    candidate = Candidate(
        version_id,
        lexical_match=True,
        matched_related_item_ids=(related_item_id,),
    )
    query = MemoryQuery(text="sharks", related_item_ids={related_item_id})
    primary = MemoryService(RetrievalManager((candidate,))).at_revision(
        REVISION.id
    ).retrieve(query)
    fallback = MemoryService(
        RetrievalManager((), (candidate,), projection_available=False)
    ).at_revision(REVISION.id).retrieve(query)

    assert primary.entries[0].match_reasons == fallback.entries[0].match_reasons
    assert primary.entries[0].score == fallback.entries[0].score


def test_pinned_retrieval_uses_the_resolved_revision_for_both_stages() -> None:
    version_id = UUID("00000000-0000-0000-0000-000000000001")
    manager = RetrievalManager((Candidate(version_id),))

    result = MemoryService(manager).at_revision(REVISION.id).retrieve(MemoryQuery())

    assert result.revision is REVISION
    assert manager.find_revisions == [REVISION]


class UnexpectedFailureManager(RetrievalManager):
    def find_candidates(self, revision, query):
        raise RuntimeError("database unavailable")


def test_retrieval_does_not_mask_unexpected_manager_failures() -> None:
    manager = UnexpectedFailureManager(())

    with pytest.raises(RuntimeError, match="database unavailable"):
        MemoryService(manager).at_revision(REVISION.id).retrieve(MemoryQuery())

    assert manager.scan_revisions == []
