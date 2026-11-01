"""Synthetic PostgreSQL coverage of bounded original-question presentation."""
from datetime import UTC, datetime
from uuid import UUID

import pytest

from backend.resources.memory.storylines import StorylineContent
from backend.services.memory import GenerationMemoryContext, MemoryMutationMetadata
from backend.services.reporter.config import ReportConfig
from backend.services.reporter.runner.tools.memory_tools import register_memory_tools
from backend.tests.database.conftest import database_engine, migrated_database
from backend.tests.services.memory.test_mutation_service import _add_generation, _seed_domain, _service
from backend.tests.services.memory.test_retrieval_service import _retrieval_service
from backend.tests.services.reporter.test_memory_tools import FrozenData, _call, _registered


@pytest.fixture
def origin_campaign(database_engine):
    domain = _seed_domain(database_engine)
    retrieval, _ = _retrieval_service(database_engine, domain)

    def begin(week, pin):
        memory = GenerationMemoryContext(
            competition_id=domain.competition_id,
            generation_id=_add_generation(database_engine, domain),
            pinned_revision_id=pin, retrieval=retrieval,
            competition_season_id=domain.season_id, week=week,
            knowledge_cutoff_at=datetime.now(UTC),
        )
        registry, *_ = _registered()
        adapter = register_memory_tools(registry, memory, FrozenData())
        return registry, memory, adapter

    def commit(memory):
        return _service(database_engine, domain).apply(memory.take_completed_bundle()).revision.revision_id

    return domain, begin, commit


def content(summary, *, headline="An acquisition question", callback="Does the acquisition improve the weekly floor?"):
    return StorylineContent(headline=headline, summary=summary, callback_condition=callback,
        status="active", salience=3, subjects=[], tags=[], evidence=[], related_storylines=[])


def seed_two_versions(campaign, *, first=None):
    domain, begin, commit = campaign
    _, memory, _ = begin(1, domain.root_revision_id)
    saved = memory.propose_storyline(first or content("An acquisition may improve the weekly floor."),
        metadata=MemoryMutationMetadata(agent_key="synthetic-arc", competition_season_id=domain.season_id, week=1))
    first_pin = commit(memory)
    _, memory, _ = begin(2, first_pin)
    memory.replace_storyline(saved.item_id, 1, content("The current assessment concerns playoff seeding.",
        callback="Can the team hold its seed?"))
    return saved.item_id, first_pin, commit(memory)


def test_original_context_is_exact_read_only_and_current_handle_stays_current(origin_campaign):
    domain, begin, commit = origin_campaign
    item, first_pin, second_pin = seed_two_versions(origin_campaign)
    registry, memory, adapter = begin(3, second_pin)
    plan = adapter.build_recall(ReportConfig.for_week(3))
    lead, = plan.result["storyline_review_pool"]
    origin = lead["original_context"]
    assert lead["summary"] == "The current assessment concerns playoff seeding."
    assert origin["summary"] == "An acquisition may improve the weekly floor."
    assert origin["callback_condition"] == "Does the acquisition improve the weekly floor?"
    assert "not current facts" in origin["provenance"]
    assert origin["relevant_week"] == 1
    assert "memory_handle" not in origin  # Origin context cannot be used as an update selector.
    bindings = [b for b in plan.metadata["bindings"] if b["result_path"][0] == "storyline_review_pool"]
    current, historical = bindings
    assert current["item_id"] == historical["item_id"] == str(item)
    assert current["expected_item_revision"] == 2 and historical["expected_item_revision"] == 1
    assert historical["result_path"] == ["storyline_review_pool", 0, "original_context"]
    assert memory.proposal_snapshot() == ()
    updated = _call(registry, "upsert_storyline_memory_card", update_handle=lead["memory_handle"],
        headline="Current assessment", summary="The original floor question remains distinguishable.")
    assert updated["saved"] is True
    proposal, = memory.proposal_snapshot()
    assert proposal.item_id == item and proposal.expected_item_revision == 2
    third_pin = commit(memory)
    # A later committed assessment cannot change the old pinned display.
    _, _, old_adapter = begin(3, second_pin)
    assert old_adapter.build_recall(ReportConfig.for_week(3)).result == plan.result
    _, _, first_adapter = begin(1, first_pin)
    first_lead, = first_adapter.build_recall(ReportConfig.for_week(1)).result["storyline_review_pool"]
    assert "original_context" not in first_lead  # No duplicated original/current card.
    assert third_pin != second_pin


def test_original_fields_are_bounded_and_clipping_is_explicit(origin_campaign):
    _, begin, _ = origin_campaign
    _, _, pin = seed_two_versions(origin_campaign, first=content("S" * 2500, headline="H" * 250, callback="Q" * 500))
    _, _, adapter = begin(3, pin)
    plan = adapter.build_recall(ReportConfig.for_week(3))
    lead, = plan.result["storyline_review_pool"]
    origin = lead["original_context"]
    assert [len(origin[k]) for k in ("headline", "summary", "callback_condition")] == [200, 2000, 400]
    assert origin["clipped"] is True
    binding = next(b for b in plan.metadata["bindings"] if b["result_path"][-1] == "original_context")
    assert set(binding["clipped_fields"]) == {"headline", "summary", "callback_condition"}
    assert "status" not in origin  # Historical active status must not look current.


def test_future_introduction_is_not_exposed_at_earlier_week(origin_campaign):
    domain, begin, commit = origin_campaign
    _, memory, _ = begin(8, domain.root_revision_id)
    saved = memory.propose_storyline(content("Future-introduced question."),
        metadata=MemoryMutationMetadata(agent_key="future-origin", competition_season_id=domain.season_id, week=2))
    pin = commit(memory)
    _, _, adapter = begin(7, pin)
    assert adapter.build_recall(ReportConfig.for_week(7)).result["storyline_review_pool"] == []


def test_filtered_original_has_no_later_version_fallback(origin_campaign):
    domain, begin, commit = origin_campaign
    _, memory, _ = begin(8, domain.root_revision_id)
    saved = memory.propose_storyline(content("Original introduced outside the report window."),
        metadata=MemoryMutationMetadata(agent_key="filtered-origin", competition_season_id=domain.season_id, week=2))
    first_pin = commit(memory)
    # A deliberately non-chronological synthetic assessment exercises filtering.
    _, memory, _ = begin(3, first_pin)
    memory.replace_storyline(saved.item_id, 1, content("Current assessment is eligible at week3."))
    second_pin = commit(memory)
    _, _, adapter = begin(3, second_pin)
    lead, = adapter.build_recall(ReportConfig.for_week(3)).result["storyline_review_pool"]
    assert lead["summary"] == "Current assessment is eligible at week3."
    assert "original_context" not in lead
