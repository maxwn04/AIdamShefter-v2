"""Tests for reporter v2 persistent context tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from reporter_memory.context_store import ContextStore
from reporter_v2.runner.tools.persistent_tools import (
    PERSISTENT_TOOL_SPECS,
    register_persistent_tools,
)
from reporter_v2.runner.tools.registry import ToolRegistry


@pytest.fixture
def store() -> ContextStore:
    context_store = ContextStore(
        ":memory:",
        league_id="league_123",
        season="2024",
    )
    yield context_store
    context_store.close()


def registered_registry(
    store: ContextStore,
    *,
    week: int = 8,
    resolve_roster_fn: Callable[[str], dict[str, Any]] | None = None,
    allow_memory_writes: bool = True,
) -> ToolRegistry:
    registry = ToolRegistry()
    register_persistent_tools(
        registry,
        store,
        week=week,
        resolve_roster_fn=resolve_roster_fn,
        allow_memory_writes=allow_memory_writes,
    )
    return registry


def decode(result: str) -> Any:
    return json.loads(result)


def test_registers_persistent_tools(store: ContextStore) -> None:
    registry = registered_registry(store)

    assert registry.tool_names[:6] == [
        "save_persistent_storyline",
        "save_team_context",
        "save_league_note",
        "load_persistent_storylines",
        "load_team_context",
        "load_league_notes",
    ]
    assert "search_story_memory" in registry.tool_names
    assert "get_memory_candidate" in registry.tool_names
    assert "save_memory_event" in registry.tool_names
    assert "upsert_storyline_memory_card" in registry.tool_names
    assert "save_storyline_trigger" in registry.tool_names
    assert "mark_memory_used" in registry.tool_names
    assert "plan_memory_verification" in registry.tool_names
    assert "record_memory_verification" in registry.tool_names
    assert registry.tool_specs == PERSISTENT_TOOL_SPECS


def test_save_and_load_storyline(store: ContextStore) -> None:
    def resolve_roster(roster_key: str) -> dict[str, Any]:
        return {"found": roster_key == "Team Taco", "roster_id": 3}

    registry = registered_registry(store, week=8, resolve_roster_fn=resolve_roster)
    save_handler = registry.get_handler("save_persistent_storyline")
    load_handler = registry.get_handler("load_persistent_storylines")

    assert save_handler is not None
    assert load_handler is not None
    save_result = decode(
        save_handler(
            id="story_2024_w8_001",
            headline="Taco Surges",
            summary="Team Taco's playoff push is getting loud.",
            status="active",
            priority=1,
            tags=["playoffs", "streak"],
            team_keys=["Team Taco", "Unknown Team"],
        )
    )
    storylines = decode(load_handler())

    assert save_result["ok"] is True
    assert save_result["saved"] is True
    assert save_result["id"] == "story_2024_w8_001"
    assert save_result["status"] == "active"
    assert save_result["team_ids"] == [3]
    assert save_result["unresolved_team_keys"] == ["Unknown Team"]
    assert len(storylines) == 1
    assert storylines[0]["id"] == "story_2024_w8_001"
    assert storylines[0]["headline"] == "Taco Surges"
    assert storylines[0]["summary"] == "Team Taco's playoff push is getting loud."
    assert storylines[0]["priority"] == 1
    assert storylines[0]["tags"] == ["playoffs", "streak"]
    assert storylines[0]["team_ids"] == [3]
    assert storylines[0]["week_created"] == 8
    assert storylines[0]["history"] == []
    assert storylines[0]["facts"] == []


def test_save_team_context(store: ContextStore) -> None:
    registry = registered_registry(store, week=9)
    save_handler = registry.get_handler("save_team_context")
    load_handler = registry.get_handler("load_team_context")

    assert save_handler is not None
    assert load_handler is not None
    save_result = decode(
        save_handler(
            roster_key="7",
            narrative="A strong contender with a fragile running back room.",
            outlook="contending",
        )
    )
    team_context = decode(load_handler())

    assert save_result == {
        "ok": True,
        "saved": True,
        "roster_id": 7,
        "roster_key": "7",
    }
    assert len(team_context) == 1
    assert team_context[0]["roster_id"] == 7
    assert team_context[0]["narrative"] == (
        "A strong contender with a fragile running back room."
    )
    assert team_context[0]["outlook"] == "contending"
    assert team_context[0]["week_last_updated"] == 9


def test_save_team_context_unresolved_team(store: ContextStore) -> None:
    registry = registered_registry(store)
    handler = registry.get_handler("save_team_context")

    assert handler is not None
    result = decode(handler(roster_key="Team Taco", narrative="Unresolved."))

    assert result == {
        "ok": False,
        "saved": False,
        "error": "Could not resolve team: Team Taco",
    }
    assert store.get_all_team_context() == []


def test_save_and_load_league_note(store: ContextStore) -> None:
    registry = registered_registry(store, week=10)
    save_handler = registry.get_handler("save_league_note")
    load_handler = registry.get_handler("load_league_notes")

    assert save_handler is not None
    assert load_handler is not None
    save_result = decode(
        save_handler(key="season_theme", value="Every contender has a flaw.")
    )
    notes = decode(load_handler())

    assert save_result == {"ok": True, "saved": True, "key": "season_theme"}
    assert notes == {"season_theme": "Every contender has a flaw."}


def test_load_empty_context(store: ContextStore) -> None:
    registry = registered_registry(store)

    load_storylines = registry.get_handler("load_persistent_storylines")
    load_team_context = registry.get_handler("load_team_context")
    load_league_notes = registry.get_handler("load_league_notes")

    assert load_storylines is not None
    assert load_team_context is not None
    assert load_league_notes is not None
    assert decode(load_storylines()) == []
    assert decode(load_team_context()) == []
    assert decode(load_league_notes()) == {}


def test_save_memory_event_and_search(store: ContextStore) -> None:
    registry = registered_registry(store, week=9)
    save_event = registry.get_handler("save_memory_event")
    upsert_card = registry.get_handler("upsert_storyline_memory_card")
    save_trigger = registry.get_handler("save_storyline_trigger")
    search = registry.get_handler("search_story_memory")
    get_candidate = registry.get_handler("get_memory_candidate")

    assert save_event is not None
    assert upsert_card is not None
    assert save_trigger is not None
    assert search is not None
    assert get_candidate is not None

    event_result = decode(
        save_event(
            id="event_trade_1",
            event_type="trade",
            week=3,
            headline="Team A sends Player X away",
            summary="Team A traded Player X to Team B.",
            importance=7,
            confidence="verified",
            source_refs=["transactions:week=3"],
            entities=[
                {
                    "entity_type": "player",
                    "entity_id": "player_x",
                    "display_name": "Player X",
                    "role": "asset_sent",
                }
            ],
        )
    )
    card_result = decode(
        upsert_card(
            id="story_trade",
            headline="Trade Arc",
            summary="A trade that may matter later.",
            status="active",
            importance=8,
            arc_type="trade_regret",
            evidence_event_ids=["event_trade_1"],
            trigger_specs=[
                {
                    "id": "trigger_trade_callback",
                    "trigger_type": "trade_evaluation",
                    "target_week": 9,
                    "condition": {"player_id": "player_x"},
                }
            ],
        )
    )
    search_result = decode(
        search(
            week=9,
            current_entities=[
                {"entity_type": "player", "entity_id": "player_x"},
            ],
        )
    )
    candidate = decode(
        get_candidate(owner_type="storyline", owner_id="story_trade")
    )

    assert event_result["ok"] is True
    assert card_result["ok"] is True
    assert card_result["linked_events"] == ["event_trade_1"]
    assert search_result["count"] >= 1
    assert search_result["candidates"][0]["owner_id"] == "story_trade"
    assert "score_components" in search_result["candidates"][0]
    assert candidate["found"] is True
    assert candidate["candidate"]["events"][0]["id"] == "event_trade_1"


def test_save_memory_event_verified_requires_source(store: ContextStore) -> None:
    registry = registered_registry(store)
    handler = registry.get_handler("save_memory_event")
    assert handler is not None

    result = decode(
        handler(
            id="event_bad",
            event_type="trade",
            week=1,
            headline="No source",
            summary="Claims verification without evidence.",
            confidence="verified",
        )
    )
    assert result["ok"] is False
    assert "source ref" in result["error"]


def test_mark_memory_used_updates_one_shot_trigger(store: ContextStore) -> None:
    registry = registered_registry(store, week=9)
    save_trigger = registry.get_handler("save_storyline_trigger")
    mark_used = registry.get_handler("mark_memory_used")
    assert save_trigger is not None
    assert mark_used is not None

    decode(
        save_trigger(
            id="trigger_1",
            trigger_type="rematch",
            target_week=9,
            fire_policy="one_shot",
        )
    )
    result = decode(
        mark_used(
            candidate_id="trigger_1",
            owner_type="trigger",
            usage="article_callback",
            reason="Used in callback paragraph.",
        )
    )

    assert result["ok"] is True
    assert result["trigger_update"] == "fired"
    trigger = store.get_trigger("trigger_1")
    assert trigger is not None
    assert trigger["status"] == "fired"
    assert trigger["fired_week"] == 9


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


def test_plan_memory_verification_returns_hints(store: ContextStore) -> None:
    _seed_trade_arc(store)
    registry = registered_registry(store, week=9)
    handler = registry.get_handler("plan_memory_verification")
    assert handler is not None

    result = decode(
        handler(
            candidate_id="story_trade",
            owner_type="storyline",
            intended_callback_claim="Player X is punishing Team A.",
        )
    )

    assert result["ok"] is True
    assert result["found"] is True
    assert result["origin_week"] == 3
    assert result["trigger_type"] == "trade_evaluation"
    assert result["required_fact_roles"] == [
        "origin_receipt",
        "current_payoff",
    ]
    assert any(
        call.startswith("transactions(week_from=3")
        for call in result["suggested_datalayer_calls"]
    )
    assert any(
        "team_game(roster_key=Team A, week=9)" in call
        for call in result["suggested_datalayer_calls"]
    )


def test_record_memory_verification_requires_roles_and_facts(
    store: ContextStore,
) -> None:
    from reporter_v2.runner.run_log import RunLog
    from reporter_v2.runner.state import ArtifactStore, ProcedureState
    from reporter_v2.runner.tools.brief_tools import save_fact
    from reporter_v2.runner.tools.context import ToolContext

    _seed_trade_arc(store)
    registry = registered_registry(store, week=9)
    ctx = ToolContext(
        artifacts=ArtifactStore(),
        procedures=ProcedureState(),
        log=RunLog(),
        turn=1,
    )
    registry.set_context(ctx)
    handler = registry.get_handler("record_memory_verification")
    assert handler is not None

    missing_roles = decode(
        handler(
            candidate_id="story_trade",
            status="verified",
            fact_links=[{"role": "origin_receipt", "fact_id": "fact_old"}],
        )
    )
    assert missing_roles["ok"] is False
    assert "origin_receipt" not in missing_roles["missing_roles"]
    assert "current_payoff" in missing_roles["missing_roles"]

    missing_facts = decode(
        handler(
            candidate_id="story_trade",
            status="verified",
            fact_links=[
                {"role": "origin_receipt", "fact_id": "fact_old"},
                {"role": "current_payoff", "fact_id": "fact_now"},
            ],
        )
    )
    assert missing_facts["ok"] is False
    assert set(missing_facts["missing_fact_ids"]) == {"fact_old", "fact_now"}

    save_fact(
        ctx,
        id="fact_old",
        claim_text="Team A traded Player X in week 3.",
        data_refs=["transactions:week=3"],
    )
    save_fact(
        ctx,
        id="fact_now",
        claim_text="Player X scored 28 against Team A in week 9.",
        data_refs=["team_game:Team A:week=9"],
    )

    result = decode(
        handler(
            candidate_id="story_trade",
            status="verified",
            fact_links=[
                {"role": "origin_receipt", "fact_id": "fact_old"},
                {"role": "current_payoff", "fact_id": "fact_now"},
            ],
            reason="Both receipt and payoff confirmed.",
        )
    )
    assert result["ok"] is True
    assert result["recorded"] is True
    assert result["status"] == "verified"
    assert result["access_id"] >= 1


def test_record_memory_verification_allows_rejection_without_facts(
    store: ContextStore,
) -> None:
    from reporter_v2.runner.run_log import RunLog
    from reporter_v2.runner.state import ArtifactStore, ProcedureState
    from reporter_v2.runner.tools.context import ToolContext

    _seed_trade_arc(store)
    registry = registered_registry(store, week=9)
    registry.set_context(
        ToolContext(
            artifacts=ArtifactStore(),
            procedures=ProcedureState(),
            log=RunLog(),
        )
    )
    handler = registry.get_handler("record_memory_verification")
    assert handler is not None

    result = decode(
        handler(
            candidate_id="story_trade",
            status="rejected",
            reason="Payoff is too weak.",
        )
    )
    assert result["ok"] is True
    assert result["status"] == "rejected"


def test_eval_mode_blocks_memory_writes_but_allows_reads(store: ContextStore) -> None:
    def resolve_roster(roster_key: str) -> dict[str, Any]:
        return {"found": roster_key == "Team Taco", "roster_id": 3}

    writable = registered_registry(store, week=8, resolve_roster_fn=resolve_roster)
    save_handler = writable.get_handler("save_persistent_storyline")
    assert save_handler is not None
    decode(
        save_handler(
            id="story_seed",
            headline="Seed Arc",
            summary="Existing memory for eval reads.",
            status="active",
            priority=1,
            tags=["seed"],
            team_keys=["Team Taco"],
        )
    )

    before = len(store.get_storylines())
    registry = registered_registry(
        store,
        week=9,
        resolve_roster_fn=resolve_roster,
        allow_memory_writes=False,
    )
    blocked_save = registry.get_handler("save_persistent_storyline")
    blocked_event = registry.get_handler("save_memory_event")
    blocked_upsert = registry.get_handler("upsert_storyline_memory_card")
    load_handler = registry.get_handler("load_persistent_storylines")
    search_handler = registry.get_handler("search_story_memory")
    assert blocked_save is not None
    assert blocked_event is not None
    assert blocked_upsert is not None
    assert load_handler is not None
    assert search_handler is not None

    save_result = decode(
        blocked_save(
            id="story_eval_should_not_persist",
            headline="Should Not Persist",
            summary="Eval mode must not write this.",
            status="active",
            priority=1,
            tags=["eval"],
            team_keys=["Team Taco"],
        )
    )
    event_result = decode(
        blocked_event(
            id="event_eval_should_not_persist",
            event_type="trade",
            week=9,
            headline="Blocked Event",
            summary="Should not hit the DB.",
        )
    )
    upsert_result = decode(
        blocked_upsert(
            id="story_eval_upsert_blocked",
            headline="Blocked Upsert",
            summary="Should not hit the DB.",
            status="active",
        )
    )
    loaded = decode(load_handler())
    searched = decode(search_handler(week=9, query="Seed"))

    assert save_result["ok"] is True
    assert save_result["saved"] is False
    assert save_result["eval_mode"] is True
    assert event_result["eval_mode"] is True
    assert upsert_result["eval_mode"] is True
    assert len(store.get_storylines()) == before
    assert any(item["id"] == "story_seed" for item in loaded)
    assert searched["ok"] is True
    assert searched["count"] >= 1
