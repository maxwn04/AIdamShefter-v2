"""Automatic recall against PostgreSQL lexical search and revision visibility."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa

from backend.database.models.core import CompetitionSeason
from backend.resources.memory.storylines import StorylineContent
from backend.services.memory import GenerationMemoryContext, MemoryMutationMetadata
from backend.services.reporter.config import ReportConfig, TimeRange
from backend.services.reporter.runner.tools.memory_tools import register_memory_tools
from backend.tests.database.conftest import database_engine, migrated_database
from backend.tests.services.memory.test_mutation_service import _add_generation, _seed_domain, _service
from backend.tests.services.memory.test_retrieval_service import _retrieval_service
from backend.tests.services.reporter.test_memory_tools import FrozenData, _call, _registered


# Exact recorded generic Week 2 request and its operational wrapper. Neither is
# a lexical relevance predicate for a Week 1 storyline.
RECORDED_WEEK_TWO_REQUEST = (
    "Write an engaging weekly league recap for week 2. Lead with the most consequential story, "
    "cover meaningful results and roster moves, follow up earlier storylines when supported, "
    "and explain what matters next. Use playoff outcomes when relevant. "
    "Simulated reporting boundary: 2025-09-19T12:00:00+00:00. Write as of this editorial time "
    "and the frozen week cutoff. These are retrospective factual inputs; their actual "
    "observation timestamps are not historical availability guarantees."
)


@pytest.fixture
def campaign(database_engine):
    domain = _seed_domain(database_engine)
    retrieval, _ = _retrieval_service(database_engine, domain)

    def begin(week, revision):
        memory = GenerationMemoryContext(
            competition_id=domain.competition_id,
            generation_id=_add_generation(database_engine, domain), pinned_revision_id=revision,
            retrieval=retrieval, competition_season_id=domain.season_id, week=week,
            knowledge_cutoff_at=datetime.now(UTC),
        )
        registry, _, _, _, _ = _registered()
        data = FrozenData()
        data.identities = {"GIBBS ME MY MONEYS": data.identities["Team Taco"].model_copy(update={
            "competition_id": domain.competition_id, "competition_season_id": domain.season_id,
            "franchise_id": domain.winner_id, "team_name": "GIBBS ME MY MONEYS",
        })}
        adapter = register_memory_tools(registry, memory, data)
        return registry, memory, adapter

    def commit(memory):
        return _service(database_engine, domain).apply(memory.take_completed_bundle()).revision.revision_id

    return domain, begin, commit


def save_lineup(registry):
    result = _call(registry, "upsert_storyline_memory_card", id="week1_lineup_precision",
        team_keys=["GIBBS ME MY MONEYS"],
        headline="Week 1 rewarded lineup precision",
        summary="GIBBS ME MY MONEYS led Week 1 with 143.84 points, while Aaron Rodgers' 25.66 remained on the bench.",
        future_callback_condition="Revisit if another win leaves a high-scoring player on the bench.")
    assert result["saved"] is True, result
    return result


def test_recorded_generic_request_recalls_and_updates_same_week_one_arc(campaign):
    domain, begin, commit = campaign
    registry, memory, _ = begin(1, domain.root_revision_id)
    saved = save_lineup(registry)
    revision = commit(memory)
    registry, memory, adapter = begin(2, revision)
    plan = adapter.build_recall(ReportConfig.for_week(2, custom_instructions=RECORDED_WEEK_TWO_REQUEST))
    lead, = plan.result["storyline_review_pool"]
    assert lead["headline"] == "Week 1 rewarded lineup precision"
    assert lead["relevant_week"] == 1
    assert "not verified current facts" in plan.result["review_pool_notice"]
    assert plan.result["likely_relevant_memories"] == []
    assert "text" not in plan.metadata["groups"]["storyline_review_pool"]["resolved_query"]
    assert memory.proposal_snapshot() == ()  # Review itself never mutates state.
    updated = _call(registry, "upsert_storyline_memory_card", update_handle=lead["memory_handle"],
        headline="Lineup precision remains worth reviewing", summary="A supported development advances the same arc.")
    assert updated["saved"] is True
    proposal, = memory.proposal_snapshot()
    assert proposal.operation == "replace"
    assert proposal.item_id == UUID(saved["proposal"]["item_id"])
    assert proposal.expected_item_revision == 1
    assert proposal.content.callback_condition == lead["callback_condition"]
    revision = commit(memory)
    _, _, adapter = begin(3, revision)
    lead, = adapter.build_recall(ReportConfig.for_week(3)).result["storyline_review_pool"]
    assert lead["headline"] == "Lineup precision remains worth reviewing"


@pytest.mark.parametrize("focus,expected", [
    ({"focus_hints": ["lineup", "unrelated meteorology"]}, 1),
    ({"focus_hints": ["unrelated meteorology"]}, 0),
    ({"focus_teams": ["GIBBS ME MY MONEYS"]}, 1),
    ({"focus_teams": ["Misspelled unknown team"]}, 0),
])
def test_explicit_focus_uses_independent_anchors_without_broad_fallback(campaign, focus, expected):
    domain, begin, commit = campaign
    registry, memory, _ = begin(1, domain.root_revision_id)
    save_lineup(registry)
    revision = commit(memory)
    _, _, adapter = begin(2, revision)
    plan = adapter.build_recall(ReportConfig(time_range=TimeRange.single_week(2), custom_instructions=RECORDED_WEEK_TWO_REQUEST, **focus))
    assert len(plan.result["likely_relevant_memories"]) == expected
    assert plan.result["storyline_review_pool"] == []


def test_pool_scope_budget_due_dedup_and_revision_pin(database_engine, campaign):
    domain, begin, commit = campaign
    other_season = uuid4()
    with database_engine.begin() as connection:
        connection.execute(sa.insert(CompetitionSeason), {
            "id": other_season, "competition_id": domain.competition_id, "season_year": 2025,
            "sequence_number": 2, "sleeper_league_id": f"other-{other_season}",
        })
    registry, memory, _ = begin(1, domain.root_revision_id)
    arc = save_lineup(registry)
    result = _call(registry, "save_storyline_trigger", id="lineup_review", trigger_type="scheduled_review",
        storyline_id=arc["id"], target_week=2, condition={"review_question": "Has the lineup edge persisted?"})
    assert result["saved"] is True
    for key, status, week, season in [
        *((f"eligible-{i}", "active", 1, domain.season_id) for i in range(4)),
        ("future", "active", 3, domain.season_id),
        ("resolved", "resolved", 1, domain.season_id),
        ("dormant", "dormant", 1, domain.season_id),
        ("wrong-season", "active", 1, other_season),
    ]:
        content = StorylineContent(headline=key, summary=f"Review {key}.", status=status,
            salience=3, tags=[], subjects=[], evidence=[], related_storylines=[])
        memory.propose_storyline(content, metadata=MemoryMutationMetadata(
            agent_key=key, competition_season_id=season, week=week))
    revision = commit(memory)
    _, memory, adapter = begin(2, revision)
    plan = adapter.build_recall(ReportConfig.for_week(2, custom_instructions=RECORDED_WEEK_TWO_REQUEST))
    assert len(plan.result["due_callbacks"]) == 1
    pool = plan.result["storyline_review_pool"]
    assert len(pool) == 3
    assert all(lead["headline"].startswith("eligible-") for lead in pool)
    group = plan.metadata["groups"]["storyline_review_pool"]
    assert group["truncated"] is True
    assert group["excluded_presented_item_ids"] == [arc["proposal"]["item_id"]]
    assert group["resolved_query"]["limit"] == 5
    assert all(binding["result_path"][:1] != ["storyline_review_pool"] or len(binding["result_path"]) == 2
               for binding in plan.metadata["bindings"])

    # Advance canonical state, then reconstruct the old pinned input unchanged.
    first_pool_binding = next(binding for binding in plan.metadata["bindings"]
                              if binding["result_path"] == ["storyline_review_pool", 0])
    replaced_id = UUID(first_pool_binding["item_id"])
    memory.replace_storyline(replaced_id, 1, StorylineContent(
        headline="Later revision", summary="Future canonical state must stay invisible at the old pin.",
        status="resolved", salience=5, tags=[], subjects=[], evidence=[], related_storylines=[]))
    new_revision = commit(memory)
    old_registry, old_memory, old_adapter = begin(2, revision)
    old_plan = old_adapter.build_recall(ReportConfig.for_week(2))
    assert old_plan.result == plan.result
    assert old_plan.metadata["pinned_revision_id"] == str(revision)
    update = _call(old_registry, "upsert_storyline_memory_card",
        update_handle=old_plan.result["storyline_review_pool"][0]["memory_handle"],
        headline="Pinned hypothesis", summary="A proposal still targets the version actually recalled.")
    assert update["saved"] is True
    proposal, = old_memory.proposal_snapshot()
    assert proposal.item_id == replaced_id and proposal.expected_item_revision == 1
    # Do not commit a historical branch: canonical stale-write checks remain in force.
    _, _, new_adapter = begin(2, new_revision)
    new_plan = new_adapter.build_recall(ReportConfig.for_week(2))
    assert len(new_plan.result["storyline_review_pool"]) == 3
    assert new_plan.metadata["groups"]["storyline_review_pool"]["truncated"] is False
