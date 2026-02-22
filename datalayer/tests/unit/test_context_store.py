"""Tests for the persistent ContextStore."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from datalayer.context_store import ContextStore, SCHEMA_VERSION


@pytest.fixture
def store(tmp_path: Path) -> ContextStore:
    """Create a ContextStore backed by a temp file."""
    return ContextStore(tmp_path / "context.db", league_id="123", season="2024")


class TestSchemaCreation:
    def test_creates_tables_on_init(self, store: ContextStore):
        cur = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row["name"] for row in cur.fetchall()}
        assert "storylines" in tables
        assert "team_context" in tables
        assert "league_context" in tables
        assert "context_meta" in tables

    def test_sets_schema_version(self, store: ContextStore):
        cur = store._conn.execute(
            "SELECT value FROM context_meta WHERE key='schema_version'"
        )
        assert cur.fetchone()["value"] == SCHEMA_VERSION

    def test_reopen_existing_db(self, tmp_path: Path):
        store1 = ContextStore(tmp_path / "ctx.db", league_id="123", season="2024")
        store1.upsert_storyline(
            {"id": "s1", "headline": "Test", "summary": "Sum", "status": "active"},
            week=1,
        )
        store1.close()

        store2 = ContextStore(tmp_path / "ctx.db", league_id="123", season="2024")
        stories = store2.get_active_storylines()
        assert len(stories) == 1
        assert stories[0]["headline"] == "Test"
        store2.close()


class TestStorylines:
    def test_upsert_create(self, store: ContextStore):
        store.upsert_storyline(
            {
                "id": "story_2024_w5_001",
                "headline": "The JT Effect",
                "summary": "iAmWeird's RB rebuild is paying off.",
                "status": "active",
                "priority": 1,
                "tags": ["trade", "streak"],
                "team_ids": [3, 7],
            },
            week=5,
        )
        stories = store.get_active_storylines()
        assert len(stories) == 1
        s = stories[0]
        assert s["id"] == "story_2024_w5_001"
        assert s["headline"] == "The JT Effect"
        assert s["priority"] == 1
        assert s["tags"] == ["trade", "streak"]
        assert s["team_ids"] == [3, 7]
        assert s["week_created"] == 5
        assert s["week_last_updated"] == 5

    def test_upsert_update(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "s1", "headline": "V1", "summary": "First", "status": "active"},
            week=5,
        )
        store.upsert_storyline(
            {"id": "s1", "headline": "V2", "summary": "Updated", "status": "active"},
            week=7,
        )
        stories = store.get_active_storylines()
        assert len(stories) == 1
        assert stories[0]["headline"] == "V2"
        assert stories[0]["summary"] == "Updated"
        # week_created should stay at 5 (INSERT ... ON CONFLICT doesn't update it)
        assert stories[0]["week_created"] == 5
        assert stories[0]["week_last_updated"] == 7

    def test_resolve_storyline(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "s1", "headline": "H", "summary": "S", "status": "active"},
            week=5,
        )
        store.resolve_storyline("s1")
        assert store.get_active_storylines() == []

        all_stories = store.get_storylines(include_resolved=True)
        assert len(all_stories) == 1
        assert all_stories[0]["status"] == "resolved"

    def test_league_scoping(self, tmp_path: Path):
        store_a = ContextStore(tmp_path / "ctx.db", league_id="AAA", season="2024")
        store_b = ContextStore(tmp_path / "ctx.db", league_id="BBB", season="2024")

        store_a.upsert_storyline(
            {"id": "s1", "headline": "A story", "summary": "S", "status": "active"},
            week=1,
        )
        store_b.upsert_storyline(
            {"id": "s2", "headline": "B story", "summary": "S", "status": "active"},
            week=1,
        )

        assert len(store_a.get_active_storylines()) == 1
        assert store_a.get_active_storylines()[0]["headline"] == "A story"
        assert len(store_b.get_active_storylines()) == 1
        assert store_b.get_active_storylines()[0]["headline"] == "B story"

    def test_priority_ordering(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "s3", "headline": "Minor", "summary": "S", "status": "active", "priority": 3},
            week=5,
        )
        store.upsert_storyline(
            {"id": "s1", "headline": "Lead", "summary": "S", "status": "active", "priority": 1},
            week=5,
        )
        stories = store.get_active_storylines()
        assert stories[0]["priority"] == 1
        assert stories[1]["priority"] == 3


class TestTeamContext:
    def test_upsert_and_get(self, store: ContextStore):
        store.upsert_team_context(
            3, "Tanking since week 6", outlook="rebuilding", week=8
        )
        ctx = store.get_team_context(3)
        assert ctx is not None
        assert ctx["narrative"] == "Tanking since week 6"
        assert ctx["outlook"] == "rebuilding"
        assert ctx["week_last_updated"] == 8

    def test_upsert_replaces(self, store: ContextStore):
        store.upsert_team_context(3, "Old note", outlook="middling", week=5)
        store.upsert_team_context(3, "New note", outlook="surging", week=8)
        ctx = store.get_team_context(3)
        assert ctx["narrative"] == "New note"
        assert ctx["outlook"] == "surging"
        assert ctx["week_last_updated"] == 8

    def test_get_nonexistent(self, store: ContextStore):
        assert store.get_team_context(999) is None

    def test_get_all(self, store: ContextStore):
        store.upsert_team_context(1, "Team 1 note", week=5)
        store.upsert_team_context(2, "Team 2 note", week=5)
        all_ctx = store.get_all_team_context()
        assert len(all_ctx) == 2
        assert all_ctx[0]["roster_id"] == 1
        assert all_ctx[1]["roster_id"] == 2


class TestLeagueContext:
    def test_upsert_and_get(self, store: ContextStore):
        store.upsert_league_context("season_theme", "Year of the trade", week=8)
        ctx = store.get_league_context()
        assert ctx["season_theme"] == "Year of the trade"

    def test_upsert_replaces(self, store: ContextStore):
        store.upsert_league_context("season_theme", "Old theme", week=5)
        store.upsert_league_context("season_theme", "New theme", week=8)
        ctx = store.get_league_context()
        assert ctx["season_theme"] == "New theme"

    def test_multiple_keys(self, store: ContextStore):
        store.upsert_league_context("season_theme", "Theme", week=5)
        store.upsert_league_context("rivalry_notes", "A vs B is heating up", week=5)
        ctx = store.get_league_context()
        assert len(ctx) == 2
        assert "season_theme" in ctx
        assert "rivalry_notes" in ctx


class TestFullContext:
    def test_empty(self, store: ContextStore):
        ctx = store.get_full_context()
        assert ctx == {
            "storylines": [],
            "team_context": [],
            "league_context": {},
        }

    def test_combined(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "s1", "headline": "H", "summary": "S", "status": "active"},
            week=5,
        )
        store.upsert_team_context(1, "Note", week=5)
        store.upsert_league_context("theme", "Value", week=5)

        ctx = store.get_full_context()
        assert len(ctx["storylines"]) == 1
        assert len(ctx["team_context"]) == 1
        assert ctx["league_context"]["theme"] == "Value"


class TestMarkStale:
    def test_marks_old_storylines(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "old", "headline": "Old", "summary": "S", "status": "active"},
            week=1,
        )
        store.upsert_storyline(
            {"id": "recent", "headline": "Recent", "summary": "S", "status": "active"},
            week=8,
        )
        count = store.mark_stale(current_week=10, weeks_threshold=4)
        assert count == 1

        active = store.get_active_storylines()
        assert len(active) == 1
        assert active[0]["id"] == "recent"

    def test_does_not_mark_resolved(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "s1", "headline": "H", "summary": "S", "status": "active"},
            week=1,
        )
        store.resolve_storyline("s1")
        count = store.mark_stale(current_week=10, weeks_threshold=4)
        assert count == 0

    def test_custom_threshold(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "s1", "headline": "H", "summary": "S", "status": "active"},
            week=5,
        )
        # With threshold=2, week 5 storyline should be stale at week 8
        count = store.mark_stale(current_week=8, weeks_threshold=2)
        assert count == 1


class TestContextToolHandlers:
    def test_get_league_memory_empty(self, store: ContextStore):
        from datalayer.context_tools import create_context_tool_handlers

        handlers = create_context_tool_handlers(store, week=5)
        result = handlers["get_league_memory"]()
        assert result["has_previous_context"] is False

    def test_get_league_memory_with_data(self, store: ContextStore):
        from datalayer.context_tools import create_context_tool_handlers

        store.upsert_storyline(
            {"id": "s1", "headline": "H", "summary": "S", "status": "active"},
            week=3,
        )
        handlers = create_context_tool_handlers(store, week=5)
        result = handlers["get_league_memory"]()
        assert result["has_previous_context"] is True
        assert len(result["storylines"]) == 1

    def test_save_storyline(self, store: ContextStore):
        from datalayer.context_tools import create_context_tool_handlers

        handlers = create_context_tool_handlers(store, week=5)
        result = handlers["save_storyline"](
            id="s1", headline="H", summary="S", status="active"
        )
        assert result["saved"] is True
        assert len(store.get_active_storylines()) == 1

    def test_save_team_context_with_int_key(self, store: ContextStore):
        from datalayer.context_tools import create_context_tool_handlers

        handlers = create_context_tool_handlers(store, week=5)
        result = handlers["save_team_context"](
            roster_key="3", narrative="Test note", outlook="contending"
        )
        assert result["saved"] is True
        ctx = store.get_team_context(3)
        assert ctx["narrative"] == "Test note"

    def test_save_league_note(self, store: ContextStore):
        from datalayer.context_tools import create_context_tool_handlers

        handlers = create_context_tool_handlers(store, week=5)
        result = handlers["save_league_note"](key="theme", value="Chaos season")
        assert result["saved"] is True
        assert store.get_league_context()["theme"] == "Chaos season"
