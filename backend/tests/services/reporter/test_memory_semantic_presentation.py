"""Hybrid discovery provenance remains an editorial lead and never a write grant."""
from uuid import uuid4
from types import SimpleNamespace

from backend.config import MemorySearchSettings
from backend.resources.memory.search_documents.objects import SearchDiscoveryStatus
from backend.services.memory import MemoryRetrievalResult, SearchDocumentQuery
from backend.services.reporter.runner.tools.memory_presentation import MemoryPresentationAdapter
from backend.tests.services.reporter.test_memory_evidence_handoff import storyline_match
from backend.tests.services.reporter.test_memory_tools import FrozenData, _call, _registered


def test_same_season_historical_search_handle_cannot_replace_current_update_target():
    current = storyline_match()
    old = current.model_copy(update={
        "current_at_pin": False,
        "memory": current.memory.model_copy(update={
            "version": current.memory.version.model_copy(update={"version_id": uuid4()}),
        }),
    })
    registry, _, memory, retrieval, adapter = _registered(matches=(current,))
    latest = _call(registry, "search_memory", text="championship")["memories"][0]
    retrieval.matches = (old,)
    earlier = _call(registry, "search_memory", text="old acquisition")["memories"][0]
    assert earlier["historical"] and earlier["read_only"]
    assert not earlier["current_at_pin"]
    assert "Superseded" in earlier["provenance"]
    assert earlier["memory_handle"] != latest["memory_handle"]
    assert adapter._pinned_agent_candidates[(current.memory.item.kind, current.memory.item.agent_key)] == current.memory
    failed = _call(registry, "upsert_storyline_memory_card", update_handle=earlier["memory_handle"],
                   headline="Must stay historical", summary="Cannot become the update target.")
    assert failed["error"]["code"] == "read_only_memory_handle"
    assert memory.proposal_snapshot() == ()
    retrieval.matches = (current,)
    again = _call(registry, "search_memory", text="championship")["memories"][0]
    assert again["memory_handle"] == latest["memory_handle"]
    assert adapter._presentation.is_read_only(earlier["memory_handle"])


def test_degraded_search_status_survives_with_successful_lexical_results():
    match = storyline_match()
    result = MemoryRetrievalResult(competition_id=match.memory.item.competition_id,
        revision_id=uuid4(), matches=(match,), semantic_status=SearchDiscoveryStatus(
            status="partial", total_count=12, available_count=3, missing_count=9,
            reason="semantic_index_incomplete"))
    presentation = MemoryPresentationAdapter(FrozenData()).present(result,
        query=SearchDocumentQuery(text="championship"), limit=8)
    assert presentation.result["memories"]
    assert presentation.result["retrieval_status"]["status"] == "partial"
    assert presentation.result["retrieval_status"]["missing_count"] == 9


def test_semantic_query_calls_require_explicit_configuration(monkeypatch):
    monkeypatch.delenv("AIDAM_MEMORY_SEMANTIC_ENABLED", raising=False)
    assert not MemorySearchSettings.from_environment().semantic_enabled
    monkeypatch.setenv("AIDAM_MEMORY_SEMANTIC_ENABLED", "true")
    settings = MemorySearchSettings.from_environment()
    assert settings.semantic_enabled
    assert (settings.embedding_model, settings.embedding_dimensions) == ("text-embedding-3-large", 3072)


def test_nested_exact_and_cross_season_links_do_not_claim_current_write_access():
    from backend.services.memory import RelatedStorylineExpansion, StorylineEvidenceExpansion
    from backend.tests.services.reporter.test_memory_presentation import (
        _event, _fact, _related_storyline, _storyline, _match,
        FrozenData as PresentationData, SEASON_ID,
    )

    old_season = uuid4()
    event = _event()
    fact = _fact(event)
    related = _related_storyline()
    related = related.model_copy(update={
        "version": related.version.model_copy(update={"competition_season_id": old_season})})
    storyline = _storyline(fact, related)

    class Data(PresentationData):
        def available_seasons(self):
            return (
                SimpleNamespace(competition_season_id=SEASON_ID, season_year=2026, role="primary"),
                SimpleNamespace(competition_season_id=old_season, season_year=2025, role="history"),
            )

        def get_roster_identity_by_canonical_id(self, *, season=None, **kwargs):
            return super().get_roster_identity_by_canonical_id(**kwargs)

    match = _match(storyline,
        exact_references=(StorylineEvidenceExpansion(reference=storyline.content.evidence[0], memory=fact),),
        stable_references=(RelatedStorylineExpansion(reference=storyline.content.related_storylines[0], memory=related),))
    adapter = MemoryPresentationAdapter(Data())
    group = adapter.present_group((match,), root="memories", limit=8)
    card = group.memories[0].model_dump(mode="json", exclude_none=True)
    exact = card["evidence"][0]
    historical = card["related_memories"][0]
    assert "current_at_pin" not in exact
    assert exact["read_only"] and adapter.is_read_only(exact["memory_handle"])
    assert historical["historical"] and historical["read_only"]
    assert adapter.is_read_only(historical["memory_handle"])
