"""Tests for the persistent ContextStore."""

from __future__ import annotations

from pathlib import Path

import pytest

from reporter_memory.context_store import ContextStore, SCHEMA_VERSION


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
        assert "storyline_history" in tables
        assert "persisted_facts" in tables

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
            {"id": "s1", "headline": "B story", "summary": "S", "status": "active"},
            week=1,
        )

        assert len(store_a.get_active_storylines()) == 1
        assert store_a.get_active_storylines()[0]["headline"] == "A story"
        assert len(store_b.get_active_storylines()) == 1
        assert store_b.get_active_storylines()[0]["headline"] == "B story"
        store_a.close()
        store_b.close()

    def test_season_scoping_same_storyline_id(self, tmp_path: Path):
        store_2024 = ContextStore(tmp_path / "ctx.db", league_id="AAA", season="2024")
        store_2025 = ContextStore(tmp_path / "ctx.db", league_id="AAA", season="2025")

        store_2024.upsert_storyline(
            {"id": "s1", "headline": "2024 story", "summary": "S", "status": "active"},
            week=1,
        )
        store_2025.upsert_storyline(
            {"id": "s1", "headline": "2025 story", "summary": "S", "status": "active"},
            week=1,
        )

        assert store_2024.get_active_storylines()[0]["headline"] == "2024 story"
        assert store_2025.get_active_storylines()[0]["headline"] == "2025 story"
        store_2024.close()
        store_2025.close()

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
    def test_save_storyline(self, store: ContextStore):
        from reporter_memory.context_tools import create_context_tool_handlers

        handlers = create_context_tool_handlers(store, week=5)
        result = handlers["save_storyline"](
            id="s1", headline="H", summary="S", status="active"
        )
        assert result["saved"] is True
        assert len(store.get_active_storylines()) == 1

    def test_save_team_context_with_int_key(self, store: ContextStore):
        from reporter_memory.context_tools import create_context_tool_handlers

        handlers = create_context_tool_handlers(store, week=5)
        result = handlers["save_team_context"](
            roster_key="3", narrative="Test note", outlook="contending"
        )
        assert result["saved"] is True
        ctx = store.get_team_context(3)
        assert ctx["narrative"] == "Test note"

    def test_save_league_note(self, store: ContextStore):
        from reporter_memory.context_tools import create_context_tool_handlers

        handlers = create_context_tool_handlers(store, week=5)
        result = handlers["save_league_note"](key="theme", value="Chaos season")
        assert result["saved"] is True
        assert store.get_league_context()["theme"] == "Chaos season"


class TestStorylineHistory:
    def test_no_history_on_create(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "s1", "headline": "H", "summary": "S", "status": "active"},
            week=5,
        )
        history = store.get_storyline_history("s1")
        assert history == []

    def test_history_appended_on_update(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "s1", "headline": "V1", "summary": "First", "status": "active"},
            week=5,
        )
        store.upsert_storyline(
            {"id": "s1", "headline": "V2", "summary": "Updated", "status": "active"},
            week=7,
        )
        history = store.get_storyline_history("s1")
        assert len(history) == 1
        assert history[0]["headline"] == "V1"
        assert history[0]["summary"] == "First"
        assert history[0]["week"] == 7

    def test_preserves_old_values(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "s1", "headline": "Original", "summary": "Sum1", "status": "active", "priority": 1},
            week=3,
        )
        store.upsert_storyline(
            {"id": "s1", "headline": "Changed", "summary": "Sum2", "status": "active", "priority": 2},
            week=5,
        )
        history = store.get_storyline_history("s1")
        assert len(history) == 1
        assert history[0]["headline"] == "Original"
        assert history[0]["summary"] == "Sum1"
        assert history[0]["priority"] == 1

    def test_chronological_ordering(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "s1", "headline": "V1", "summary": "S", "status": "active"},
            week=3,
        )
        store.upsert_storyline(
            {"id": "s1", "headline": "V2", "summary": "S", "status": "active"},
            week=5,
        )
        store.upsert_storyline(
            {"id": "s1", "headline": "V3", "summary": "S", "status": "active"},
            week=7,
        )
        history = store.get_storyline_history("s1")
        assert len(history) == 2
        assert history[0]["headline"] == "V1"
        assert history[1]["headline"] == "V2"

    def test_multiple_updates_create_multiple_rows(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "s1", "headline": "V1", "summary": "S", "status": "active"},
            week=1,
        )
        for w in range(2, 6):
            store.upsert_storyline(
                {"id": "s1", "headline": f"V{w}", "summary": "S", "status": "active"},
                week=w,
            )
        history = store.get_storyline_history("s1")
        assert len(history) == 4  # 4 updates after the initial create

    def test_history_scoped_by_league(self, tmp_path: Path):
        store_a = ContextStore(tmp_path / "ctx.db", league_id="AAA", season="2024")
        store_b = ContextStore(tmp_path / "ctx.db", league_id="BBB", season="2024")

        store_a.upsert_storyline(
            {"id": "s1", "headline": "A v1", "summary": "S", "status": "active"},
            week=1,
        )
        store_b.upsert_storyline(
            {"id": "s1", "headline": "B v1", "summary": "S", "status": "active"},
            week=1,
        )
        store_a.upsert_storyline(
            {"id": "s1", "headline": "A v2", "summary": "S", "status": "active"},
            week=2,
        )
        store_b.upsert_storyline(
            {"id": "s1", "headline": "B v2", "summary": "S", "status": "active"},
            week=2,
        )

        assert store_a.get_storyline_history("s1")[0]["headline"] == "A v1"
        assert store_b.get_storyline_history("s1")[0]["headline"] == "B v1"
        store_a.close()
        store_b.close()


class TestPersistedFacts:
    def test_basic_persistence(self, store: ContextStore):
        facts = [
            {"id": "fact_001", "claim_text": "Josh Allen scored 38.7", "data_refs": ["week_games:week=1"], "numbers": {"points": 38.7}, "category": "score"},
        ]
        count = store.persist_facts(facts, "story_1", week=5)
        assert count == 1

        stored = store.get_storyline_facts("story_1")
        assert len(stored) == 1
        assert stored[0]["claim_text"] == "Josh Allen scored 38.7"
        assert stored[0]["data_refs"] == ["week_games:week=1"]
        assert stored[0]["numbers"] == {"points": 38.7}
        assert stored[0]["category"] == "score"

    def test_deduplication(self, store: ContextStore):
        facts = [
            {"id": "fact_001", "claim_text": "Claim A"},
        ]
        count1 = store.persist_facts(facts, "story_1", week=5)
        count2 = store.persist_facts(facts, "story_1", week=5)
        assert count1 == 1
        assert count2 == 0

        stored = store.get_storyline_facts("story_1")
        assert len(stored) == 1

    def test_same_fact_id_different_weeks(self, store: ContextStore):
        facts = [{"id": "fact_001", "claim_text": "Week 5 version"}]
        store.persist_facts(facts, "story_1", week=5)

        facts2 = [{"id": "fact_001", "claim_text": "Week 6 version"}]
        store.persist_facts(facts2, "story_1", week=6)

        stored = store.get_storyline_facts("story_1")
        assert len(stored) == 2

    def test_retrieval_by_storyline(self, store: ContextStore):
        store.persist_facts(
            [{"id": "f1", "claim_text": "Fact for story A"}],
            "story_a",
            week=5,
        )
        store.persist_facts(
            [{"id": "f2", "claim_text": "Fact for story B"}],
            "story_b",
            week=5,
        )

        facts_a = store.get_storyline_facts("story_a")
        facts_b = store.get_storyline_facts("story_b")
        assert len(facts_a) == 1
        assert len(facts_b) == 1
        assert facts_a[0]["claim_text"] == "Fact for story A"
        assert facts_b[0]["claim_text"] == "Fact for story B"

    def test_facts_scoped_by_league(self, tmp_path: Path):
        store_a = ContextStore(tmp_path / "ctx.db", league_id="AAA", season="2024")
        store_b = ContextStore(tmp_path / "ctx.db", league_id="BBB", season="2024")

        store_a.persist_facts(
            [{"id": "f1", "claim_text": "A fact"}],
            "s1",
            week=5,
        )
        store_b.persist_facts(
            [{"id": "f1", "claim_text": "B fact"}],
            "s1",
            week=5,
        )

        assert store_a.get_storyline_facts("s1")[0]["claim_text"] == "A fact"
        assert store_b.get_storyline_facts("s1")[0]["claim_text"] == "B fact"
        store_a.close()
        store_b.close()


class TestEnrichedStorylines:
    def test_includes_history_and_facts(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "s1", "headline": "V1", "summary": "S", "status": "active"},
            week=3,
        )
        store.upsert_storyline(
            {"id": "s1", "headline": "V2", "summary": "Updated", "status": "active"},
            week=5,
        )
        store.persist_facts(
            [{"id": "f1", "claim_text": "Some fact"}],
            "s1",
            week=5,
        )

        enriched = store.get_enriched_storylines(["s1"])
        assert len(enriched) == 1
        assert enriched[0]["headline"] == "V2"
        assert len(enriched[0]["history"]) == 1
        assert enriched[0]["history"][0]["headline"] == "V1"
        assert len(enriched[0]["facts"]) == 1
        assert enriched[0]["facts"][0]["claim_text"] == "Some fact"

    def test_handles_empty_history(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "s1", "headline": "Fresh", "summary": "S", "status": "active"},
            week=5,
        )
        enriched = store.get_enriched_storylines(["s1"])
        assert len(enriched) == 1
        assert enriched[0]["history"] == []
        assert enriched[0]["facts"] == []

    def test_respects_history_cap(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "s1", "headline": "V0", "summary": "S", "status": "active"},
            week=1,
        )
        for w in range(2, 12):
            store.upsert_storyline(
                {"id": "s1", "headline": f"V{w}", "summary": "S", "status": "active"},
                week=w,
            )
        enriched = store.get_enriched_storylines(["s1"])
        assert len(enriched[0]["history"]) == 6  # capped at 6

    def test_respects_facts_cap(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "s1", "headline": "H", "summary": "S", "status": "active"},
            week=1,
        )
        for i in range(20):
            store.persist_facts(
                [{"id": f"f{i}", "claim_text": f"Fact {i}"}],
                "s1",
                week=i + 1,
            )
        enriched = store.get_enriched_storylines(["s1"])
        assert len(enriched[0]["facts"]) == 15  # capped at 15

    def test_empty_ids(self, store: ContextStore):
        assert store.get_enriched_storylines([]) == []

    def test_enriched_storylines_scoped_by_league(self, tmp_path: Path):
        store_a = ContextStore(tmp_path / "ctx.db", league_id="AAA", season="2024")
        store_b = ContextStore(tmp_path / "ctx.db", league_id="BBB", season="2024")

        store_a.upsert_storyline(
            {"id": "s1", "headline": "A story", "summary": "S", "status": "active"},
            week=1,
        )
        store_b.upsert_storyline(
            {"id": "s1", "headline": "B story", "summary": "S", "status": "active"},
            week=1,
        )

        assert store_a.get_enriched_storylines(["s1"])[0]["headline"] == "A story"
        assert store_b.get_enriched_storylines(["s1"])[0]["headline"] == "B story"
        store_a.close()
        store_b.close()


class TestStorylineSummaries:
    def test_returns_active_and_stale(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "s1", "headline": "Active", "summary": "S", "status": "active"},
            week=8,
        )
        store.upsert_storyline(
            {"id": "s2", "headline": "Old", "summary": "S", "status": "active"},
            week=1,
        )
        store.mark_stale(current_week=10, weeks_threshold=4)

        summaries = store.get_storyline_summaries()
        assert len(summaries) == 2
        statuses = {s["status"] for s in summaries}
        assert statuses == {"active", "stale"}

    def test_excludes_resolved(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "s1", "headline": "H", "summary": "S", "status": "active"},
            week=5,
        )
        store.resolve_storyline("s1")
        summaries = store.get_storyline_summaries()
        assert summaries == []

    def test_returns_expected_fields(self, store: ContextStore):
        store.upsert_storyline(
            {"id": "s1", "headline": "H", "summary": "Sum", "status": "active",
             "priority": 1, "tags": ["streak"], "team_ids": [3]},
            week=5,
        )
        summaries = store.get_storyline_summaries()
        s = summaries[0]
        assert s["id"] == "s1"
        assert s["headline"] == "H"
        assert s["summary"] == "Sum"
        assert s["priority"] == 1
        assert s["tags"] == ["streak"]
        assert s["team_ids"] == [3]
        assert s["week_created"] == 5
        assert s["week_last_updated"] == 5


class TestSchemaMigration:
    def test_legacy_schema_is_rejected(self, tmp_path: Path):
        """Old schema versions are rejected instead of migrated."""
        import sqlite3

        db_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(str(db_path))
        # Create v1 schema manually (without new tables)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS context_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS storylines (
                id TEXT PRIMARY KEY,
                league_id TEXT NOT NULL,
                season TEXT NOT NULL,
                headline TEXT NOT NULL,
                summary TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                priority INTEGER NOT NULL DEFAULT 2,
                tags TEXT,
                team_ids TEXT,
                week_created INTEGER NOT NULL,
                week_last_updated INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS team_context (
                league_id TEXT NOT NULL,
                season TEXT NOT NULL,
                roster_id INTEGER NOT NULL,
                narrative TEXT NOT NULL,
                outlook TEXT,
                week_last_updated INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (league_id, season, roster_id)
            );
            CREATE TABLE IF NOT EXISTS league_context (
                league_id TEXT NOT NULL,
                season TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                week_last_updated INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (league_id, season, key)
            );
            INSERT INTO context_meta (key, value) VALUES ('schema_version', '1');
        """)
        conn.close()

        with pytest.raises(RuntimeError, match="Unsupported reporter memory schema"):
            ContextStore(db_path, league_id="123", season="2024")

    def test_fresh_db_starts_at_current_schema(self, store: ContextStore):
        cur = store._conn.execute(
            "SELECT value FROM context_meta WHERE key='schema_version'"
        )
        assert cur.fetchone()["value"] == SCHEMA_VERSION
