"""Tests for reporter_memory search and candidate expansion."""

from __future__ import annotations

import pytest

from reporter_memory.context_store import ContextStore
from reporter_memory.search import (
    get_memory_candidate,
    plan_memory_verification,
    search_story_memory,
)


@pytest.fixture
def store() -> ContextStore:
    context_store = ContextStore(
        ":memory:",
        league_id="league_123",
        season="2024",
    )
    yield context_store
    context_store.close()


def _seed_trade_arc(store: ContextStore) -> None:
    store.upsert_storyline(
        {
            "id": "story_trade",
            "headline": "Trade Arc",
            "summary": "Team A sent Player X away and may regret it.",
            "status": "active",
            "importance": 8,
            "arc_type": "trade_regret",
            "tags": ["trade", "regret"],
            "team_ids": [1],
        },
        week=3,
    )
    store.upsert_story_event(
        {
            "id": "event_trade_1",
            "week": 3,
            "event_type": "trade",
            "headline": "Team A sends Player X away",
            "summary": "Team A traded Player X to Team B.",
            "importance": 7,
            "confidence": "verified",
            "source_refs": ["transactions:week=3"],
            "transaction_id": "txn_123",
        }
    )
    store.replace_story_event_entities(
        "event_trade_1",
        [
            {
                "entity_type": "team",
                "entity_id": "1",
                "display_name": "Team A",
                "role": "seller",
            },
            {
                "entity_type": "player",
                "entity_id": "player_x",
                "display_name": "Player X",
                "role": "asset_sent",
            },
        ],
    )
    store.link_storyline_event("story_trade", "event_trade_1", "origin")
    store.upsert_storyline_trigger(
        {
            "id": "trigger_trade_callback",
            "storyline_id": "story_trade",
            "event_id": "event_trade_1",
            "trigger_type": "trade_evaluation",
            "target_week": 9,
            "condition": {"player_id": "player_x", "former_roster_id": 1},
            "fire_policy": "one_shot",
        }
    )


def test_search_by_trigger_target_week(store: ContextStore) -> None:
    _seed_trade_arc(store)

    results = search_story_memory(store, week=9, limit=5)

    assert results
    top = results[0]
    assert top["owner_type"] == "storyline"
    assert top["owner_id"] == "story_trade"
    assert top["score_components"]["trigger_match"] >= 30
    assert any(
        trigger["id"] == "trigger_trade_callback"
        for trigger in top["matched_triggers"]
    )


def test_search_by_entity_overlap(store: ContextStore) -> None:
    _seed_trade_arc(store)

    results = search_story_memory(
        store,
        week=8,
        current_entities=[
            {"entity_type": "player", "entity_id": "player_x"},
        ],
        limit=5,
    )

    assert any(item["owner_id"] == "story_trade" for item in results)
    match = next(item for item in results if item["owner_id"] == "story_trade")
    assert match["score_components"]["entity_overlap"] > 0
    assert match["score_components"]["trigger_match"] >= 20


def test_search_by_fts_query(store: ContextStore) -> None:
    _seed_trade_arc(store)

    results = search_story_memory(
        store,
        week=8,
        query="regret Player X",
        limit=5,
    )

    assert any(item["owner_id"] == "story_trade" for item in results)
    match = next(item for item in results if item["owner_id"] == "story_trade")
    assert match["score_components"]["lexical_score"] > 0


def test_search_excludes_resolved_by_default(store: ContextStore) -> None:
    _seed_trade_arc(store)
    store.resolve_storyline("story_trade")

    default_results = search_story_memory(store, week=9, limit=5)
    included = search_story_memory(
        store, week=9, include_resolved=True, limit=5
    )

    assert all(item["owner_id"] != "story_trade" for item in default_results)
    assert any(item["owner_id"] == "story_trade" for item in included)


def test_get_memory_candidate_expands_storyline(store: ContextStore) -> None:
    _seed_trade_arc(store)
    store.persist_facts(
        [{"id": "fact_trade", "claim_text": "Team A traded Player X."}],
        "story_trade",
        week=3,
    )

    candidate = get_memory_candidate(store, "storyline", "story_trade")

    assert candidate is not None
    assert candidate["owner_type"] == "storyline"
    assert candidate["storyline"]["id"] == "story_trade"
    assert candidate["events"][0]["id"] == "event_trade_1"
    assert candidate["triggers"][0]["id"] == "trigger_trade_callback"
    assert candidate["persisted_facts"][0]["fact_id"] == "fact_trade"
    assert "transactions:week=3" in candidate["source_refs"]


def test_plan_memory_verification_for_trade_arc(store: ContextStore) -> None:
    _seed_trade_arc(store)

    plan = plan_memory_verification(
        store,
        candidate_id="story_trade",
        owner_type="storyline",
        current_week=9,
        intended_callback_claim="Player X is a trade regret.",
    )

    assert plan is not None
    assert plan["found"] is True
    assert plan["origin_week"] == 3
    assert plan["event_type"] == "trade"
    assert plan["trigger_type"] == "trade_evaluation"
    assert plan["required_fact_roles"] == ["origin_receipt", "current_payoff"]
    assert "transactions(week_from=3, week_to=3)" in plan["suggested_datalayer_calls"]
    assert any(
        "player_weekly_log(player_key=Player X" in call
        for call in plan["suggested_datalayer_calls"]
    )


def test_search_scoped_by_league(tmp_path) -> None:
    store_a = ContextStore(tmp_path / "ctx.db", league_id="AAA", season="2024")
    store_b = ContextStore(tmp_path / "ctx.db", league_id="BBB", season="2024")
    _seed_trade_arc(store_a)
    store_b.upsert_storyline(
        {
            "id": "story_trade",
            "headline": "Other League Arc",
            "summary": "Should not leak.",
            "status": "active",
        },
        week=3,
    )

    results = search_story_memory(store_a, week=9, query="regret", limit=5)
    assert results
    assert all(
        item["headline"] != "Other League Arc" for item in results
    )
    store_a.close()
    store_b.close()
