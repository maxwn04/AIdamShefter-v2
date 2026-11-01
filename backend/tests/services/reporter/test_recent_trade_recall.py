"""Synthetic PostgreSQL coverage for bounded, revision-safe trade discovery."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import sqlalchemy as sa

from backend.database.models.core import CompetitionSeason
from backend.resources.memory.events import EventContent
from backend.resources.memory.search_documents import SearchDocumentQuery
from backend.services.memory import GenerationMemoryContext, MemoryKind, MemoryMutationMetadata
from backend.services.reporter.config import ReportConfig, TimeRange
from backend.services.reporter.runner.tools.memory_tools import register_memory_tools
from backend.tests.database.conftest import database_engine, migrated_database
from backend.tests.services.memory.test_mutation_service import _add_generation, _event, _seed_domain, _service
from backend.tests.services.memory.test_retrieval_service import _retrieval_service
from backend.tests.services.reporter.test_memory_tools import FrozenData, _registered


def trade(domain, name, *, salience=1, status="active"):
    return EventContent.model_validate({
        "event_type": "trade", "headline": name, "summary": f"Recorded transfer {name}.",
        "salience": salience, "confidence": "inferred", "status": status,
        "details": {"kind": "trade", "assets": [{
            "kind": "budget", "amount": 5,
            "from_franchise_id": domain.winner_id, "to_franchise_id": domain.loser_id,
        }]},
    })


def begin(engine, domain, week, pin):
    retrieval, _ = _retrieval_service(engine, domain)
    memory = GenerationMemoryContext(
        competition_id=domain.competition_id, generation_id=_add_generation(engine, domain),
        pinned_revision_id=pin, retrieval=retrieval, competition_season_id=domain.season_id,
        week=week, knowledge_cutoff_at=datetime.now(UTC),
    )
    registry, *_ = _registered()
    data = FrozenData()
    data.identities = {"Owls": data.identities["Team Taco"].model_copy(update={
        "competition_id": domain.competition_id, "competition_season_id": domain.season_id,
        "franchise_id": domain.winner_id, "team_name": "Owls",
    })}
    return memory, register_memory_tools(registry, memory, data)


def commit(engine, domain, memory):
    return _service(engine, domain).apply(memory.take_completed_bundle()).revision.revision_id


def add(memory, domain, content, week, *, season=None):
    return memory.propose_event(content, metadata=MemoryMutationMetadata(
        competition_season_id=season or domain.season_id, week=week,
    ))


def test_generic_recall_filters_typed_trades_before_limit_and_uses_source_week(database_engine):
    domain = _seed_domain(database_engine)
    other_season = uuid4()
    with database_engine.begin() as connection:
        connection.execute(sa.insert(CompetitionSeason), {
            "id": other_season, "competition_id": domain.competition_id,
            "season_year": 2027, "sequence_number": 2, "sleeper_league_id": f"other-{other_season}",
        })
    memory, _ = begin(database_engine, domain, 4, domain.root_revision_id)
    refs = [add(memory, domain, trade(domain, f"trade-{week}", salience=5 if week == 1 else 1), week)
            for week in range(1, 5)]
    for _ in range(8):
        add(memory, domain, _event(domain), 4)  # Higher-salience non-trades cannot consume the bound.
    add(memory, domain, trade(domain, "future-origin"), 9)
    add(memory, domain, trade(domain, "wrong-season"), 4, season=other_season)
    add(memory, domain, trade(domain, "archived", status="archived"), 4)
    first = commit(database_engine, domain, memory)
    memory, _ = begin(database_engine, domain, 5, first)
    memory.replace_event(refs[0].item_id, 1, trade(domain, "old-event-rewritten", salience=5),
                         metadata=MemoryMutationMetadata(competition_season_id=domain.season_id, week=1))
    latest = commit(database_engine, domain, memory)
    foreign = _seed_domain(database_engine)
    foreign_memory, _ = begin(database_engine, foreign, 5, foreign.root_revision_id)
    add(foreign_memory, foreign, trade(foreign, "another-competition"), 5)
    commit(database_engine, foreign, foreign_memory)
    memory, adapter = begin(database_engine, domain, 5, latest)
    plan = adapter.build_recall(ReportConfig.for_week(5, custom_instructions="A general league recap."))
    cards = plan.result["likely_relevant_memories"]
    assert [card["headline"] for card in cards] == ["trade-4", "trade-3", "trade-2"]
    assert [card["relevant_week"] for card in cards] == [4, 3, 2]
    group = plan.metadata["groups"]["likely_relevant_memories"]
    assert group["truncated"] is True and group["selected_count"] == 4
    assert len(cards) == 3  # The fourth candidate only signals truncation.
    assert group["resolved_query"]["recent_trade_events"] is True
    assert group["resolved_query"]["limit"] == 4
    assert memory.proposal_snapshot() == ()
    bindings = [b for b in plan.metadata["bindings"] if b["result_path"][0] == "likely_relevant_memories"]
    assert {b["item_id"] for b in bindings if len(b["result_path"]) == 2} == {str(r.item_id) for r in refs[1:]}


def test_trade_recall_keeps_old_pin_and_excludes_future_introduction(database_engine):
    domain = _seed_domain(database_engine)
    memory, _ = begin(database_engine, domain, 2, domain.root_revision_id)
    ref = add(memory, domain, trade(domain, "original"), 2)
    first = commit(database_engine, domain, memory)
    memory, _ = begin(database_engine, domain, 8, first)
    memory.replace_event(ref.item_id, 1, trade(domain, "later-assessment"),
                         metadata=MemoryMutationMetadata(competition_season_id=domain.season_id, week=2))
    latest = commit(database_engine, domain, memory)
    _, old = begin(database_engine, domain, 7, first)
    old_plan = old.build_recall(ReportConfig.for_week(7))
    assert [c["headline"] for c in old_plan.result["likely_relevant_memories"]] == ["original"]
    _, bounded = begin(database_engine, domain, 7, latest)
    assert bounded.build_recall(ReportConfig.for_week(7)).result["likely_relevant_memories"] == []
    _, current = begin(database_engine, domain, 8, latest)
    assert [c["headline"] for c in current.build_recall(ReportConfig.for_week(8)).result["likely_relevant_memories"]] == ["later-assessment"]


def test_explicit_unresolved_focus_does_not_get_a_broad_trade_fallback(database_engine):
    domain = _seed_domain(database_engine)
    memory, _ = begin(database_engine, domain, 2, domain.root_revision_id)
    add(memory, domain, trade(domain, "eligible"), 2)
    pin = commit(database_engine, domain, memory)
    _, adapter = begin(database_engine, domain, 3, pin)
    plan = adapter.build_recall(ReportConfig(time_range=TimeRange.single_week(3), focus_teams=["Unknown team"]))
    assert plan.result["likely_relevant_memories"] == []
    assert plan.metadata["groups"]["likely_relevant_memories"].get("resolved_query") is None


@pytest.mark.parametrize("arguments", [{"text": "trade"}, {"include_history": True}, {"kinds": (MemoryKind.STORYLINE,)}])
def test_recent_trade_mode_cannot_replace_focused_or_historical_search(arguments):
    with pytest.raises(ValueError, match="current event-only"):
        SearchDocumentQuery(**{"kinds": (MemoryKind.EVENT,), "recent_trade_events": True, **arguments})
