"""Hybrid relevance tests use deterministic scores, never provider calls."""
from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine

from backend.database.sessions import create_session_factory
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.search_documents import SearchDocumentManager, SearchDocumentQuery, SearchMatchReason
from backend.resources.memory.search_documents.semantic import EmbeddingDocument, SemanticSearchResult
from backend.services.memory import MemoryMutationOrigin
from backend.tests.database.conftest import database_engine, migrated_database
from backend.tests.resources.memory.test_search_document_manager import _committed_bundle
from backend.tests.services.memory.test_mutation_service import _add_generation, _fact, _service, _storyline


class Scores:
    def __init__(self, values: dict[UUID, float], *, status: str = "ready") -> None:
        self.values = values
        self.status = status
        self.seen: list[tuple[EmbeddingDocument, ...]] = []

    def score(self, query: str, documents: Sequence[EmbeddingDocument]) -> SemanticSearchResult:
        self.seen.append(tuple(documents))
        return SemanticSearchResult(
            scores=self.values, status=self.status, total_count=len(documents),
            available_count=len(documents) if self.status == "ready" else 0,
            reason="Fixture relevance scores, not real embeddings.",
        )


def manager_with_scores(engine: Engine, competition_id: UUID, scorer: Scores) -> SearchDocumentManager:
    context = ManagerContext[CompetitionScope].model_validate({
        "actor": {"kind": "system_process", "process_name": "hybrid-test"},
        "scope": {"kind": "competition", "competition_id": competition_id},
        "correlation_id": uuid4(),
    })
    return SearchDocumentManager(create_session_factory(engine), context, semantic_index=scorer)


def test_semantic_strategy_receives_only_hard_scoped_units(database_engine: Engine) -> None:
    domain, ids, pin = _committed_bundle(database_engine)
    other, other_ids, _ = _committed_bundle(database_engine)
    scorer = Scores({ids["storyline_version"]: .85, other_ids["storyline_version"]: .99})
    manager = manager_with_scores(database_engine, domain.competition_id, scorer)
    query = SearchDocumentQuery(
        text="championship ambition", kinds=(MemoryKind.STORYLINE,), statuses=("active",),
        required_entity_keys=(f"franchise:{domain.winner_id}",),
        allowed_season_weeks={domain.season_id: 7}, week_from=7, week_to=7,
    )
    result = manager.discover(pin, query)
    assert [x.version_id for x in result.candidates] == [ids["storyline_version"]]
    assert {x.version_id for x in scorer.seen[-1]} == {ids["storyline_version"]}
    assert result.candidates[0].match_reasons == (SearchMatchReason.SEMANTIC_MATCH,)
    assert result.semantic_status.status == "ready"
    for update in (
        {"required_entity_keys": (f"franchise:{other.winner_id}",)},
        {"allowed_season_weeks": {domain.season_id: 6}},
        {"statuses": ("resolved",)}, {"season": 1990},
        {"competition_season_id": other.season_id},
    ):
        assert manager.discover(pin, query.model_copy(update=update)).candidates == ()
        assert scorer.seen[-1] == ()


def test_historical_search_selects_exact_best_version_without_duplicate_arc(database_engine: Engine) -> None:
    domain, ids, first = _committed_bundle(database_engine)
    replacement = _service(database_engine, domain).replace_storyline(MemoryMutationOrigin(
        generation_id=_add_generation(database_engine, domain), expected_revision_id=first,
        competition_season_id=domain.season_id, week=8,
    ), ids["storyline_item"], 1, _storyline(domain, ids["event_version"], ids["fact_version"]).model_copy(update={
        "headline": "Owls finish first", "summary": "Their final bracket game settled the season.",
        "tags": [], "arc_type": "title_run", "callback_condition": None,
    }))
    assert replacement.revision is not None
    latest = replacement.changes[0].version_id
    scorer = Scores({ids["storyline_version"]: .9, latest: .4})
    manager = manager_with_scores(database_engine, domain.competition_id, scorer)
    query = SearchDocumentQuery(text="receiver acquisition payoff", include_history=True, kinds=(MemoryKind.STORYLINE,))
    after = manager.discover(replacement.revision.revision_id, query)
    assert len(after.candidates) == 1
    assert after.candidates[0].version_id == ids["storyline_version"]
    assert after.candidates[0].current_at_pin is False
    assert after.candidates[0].revision_number == 1
    assert manager.inspect_versions(replacement.revision.revision_id, after.candidates[0].version_id)[0][0] == ids["storyline_version"]
    before = manager.discover(first, query)
    assert before.candidates[0].current_at_pin is True
    assert {x.version_id for x in scorer.seen[-1]} == {ids["storyline_version"]}
    current_only = manager.discover(replacement.revision.revision_id, query.model_copy(update={"include_history": False}))
    assert current_only.candidates[0].version_id == latest
    assert current_only.candidates[0].revision_number == 2
    manager.discover(replacement.revision.revision_id, query.model_copy(update={"allowed_season_weeks": {domain.season_id: 7}}))
    assert {x.version_id for x in scorer.seen[-1]} == {ids["storyline_version"]}


def test_degraded_semantics_preserve_lexical_and_no_support_is_empty(database_engine: Engine) -> None:
    domain, ids, pin = _committed_bundle(database_engine)
    scorer = Scores({}, status="unavailable")
    manager = manager_with_scores(database_engine, domain.competition_id, scorer)
    lexical = manager.discover(pin, SearchDocumentQuery(text="playoff", kinds=(MemoryKind.STORYLINE,)))
    assert lexical.candidates[0].version_id == ids["storyline_version"]
    assert lexical.semantic_status.status == "unavailable"
    assert manager.discover(pin, SearchDocumentQuery(text="interstellar scuba expedition")).candidates == ()
    scorer.values = {ids["storyline_version"]: .12}
    assert manager.discover(pin, SearchDocumentQuery(text="interstellar scuba expedition")).candidates == ()


def test_historical_fact_versions_are_not_discovery_units(database_engine: Engine) -> None:
    domain, ids, first = _committed_bundle(database_engine)
    replaced = _service(database_engine, domain).replace_fact(MemoryMutationOrigin(
        generation_id=_add_generation(database_engine, domain), expected_revision_id=first,
        competition_season_id=domain.season_id, week=8,
    ), ids["fact_item"], 1, _fact(domain, ids["event_version"], archived=True))
    assert replaced.revision is not None
    latest = replaced.changes[0].version_id
    scorer = Scores({ids["fact_version"]: .99, latest: .8})
    manager = manager_with_scores(database_engine, domain.competition_id, scorer)
    result = manager.discover(replaced.revision.revision_id, SearchDocumentQuery(text="close result", include_history=True, kinds=(MemoryKind.FACT,)))
    assert {x.version_id for x in scorer.seen[-1]} == {latest}
    assert result.candidates[0].current_at_pin is True


def test_structured_browse_does_not_call_semantic_provider(database_engine: Engine) -> None:
    domain, _, pin = _committed_bundle(database_engine)
    scorer = Scores({})
    result = manager_with_scores(database_engine, domain.competition_id, scorer).discover(pin, SearchDocumentQuery(include_history=True))
    assert result.candidates
    assert scorer.seen == []
    assert all(candidate.current_at_pin for candidate in result.candidates)


def test_rank_fusion_collapses_versions_without_pushing_other_items_down() -> None:
    from backend.resources.memory.search_documents.objects import SearchDocumentCandidate, SearchScoreComponents
    from backend.resources.memory.search_documents.ranking import rank_candidates

    arc, distractor = uuid4(), uuid4()
    old_id, current_id, other_id = uuid4(), uuid4(), uuid4()
    candidates = [
        SearchDocumentCandidate(
            version_id=version_id, item_id=item_id, kind=MemoryKind.STORYLINE,
            current_at_pin=current, revision_number=revision, score=0,
            score_components=SearchScoreComponents(), match_reasons=(),
        )
        for version_id, item_id, current, revision in (
            (old_id, arc, False, 1), (current_id, arc, True, 2),
            (other_id, distractor, True, 1),
        )
    ]
    ranked = rank_candidates(candidates, SearchDocumentQuery(text="title payoff"), {
        old_id: .8, current_id: .8, other_id: .7,
    })
    assert [candidate.version_id for candidate in ranked] == [current_id, other_id]
    assert ranked[0].score == 1 / 61
    assert ranked[1].score == 1 / 62
