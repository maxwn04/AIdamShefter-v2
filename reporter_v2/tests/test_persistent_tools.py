"""Tests for reporter v2 persistent context tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from datalayer.context_store import ContextStore
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
) -> ToolRegistry:
    registry = ToolRegistry()
    register_persistent_tools(
        registry,
        store,
        week=week,
        resolve_roster_fn=resolve_roster_fn,
    )
    return registry


def decode(result: str) -> Any:
    return json.loads(result)


def test_registers_persistent_tools(store: ContextStore) -> None:
    registry = registered_registry(store)

    assert registry.tool_names == [
        "save_persistent_storyline",
        "save_team_context",
        "save_league_note",
        "load_persistent_storylines",
        "load_team_context",
        "load_league_notes",
    ]
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

    assert save_result == {
        "ok": True,
        "saved": True,
        "id": "story_2024_w8_001",
        "status": "active",
        "team_ids": [3],
        "unresolved_team_keys": ["Unknown Team"],
    }
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
