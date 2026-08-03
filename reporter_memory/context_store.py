"""Persistent context store for cross-run agent memory.

Stores storylines, team context, and league-wide notes in a file-backed
SQLite database. This gives the research agent memory across runs while
keeping the existing fresh-load pattern for Sleeper API data.

Usage:
    store = ContextStore(".data/context.db", league_id="123", season="2024")
    context = store.get_full_context()
    store.upsert_storyline({...})
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "3"

_DDL = """
CREATE TABLE IF NOT EXISTS context_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS storylines (
    id TEXT NOT NULL,
    league_id TEXT NOT NULL,
    season TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    priority INTEGER NOT NULL DEFAULT 2,
    arc_type TEXT,
    importance INTEGER NOT NULL DEFAULT 4,
    origin_week INTEGER,
    future_callback_condition TEXT,
    tags TEXT,
    team_ids TEXT,
    week_created INTEGER NOT NULL,
    week_last_updated INTEGER NOT NULL,
    last_accessed_week INTEGER,
    last_accessed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (league_id, season, id)
);
CREATE INDEX IF NOT EXISTS idx_storylines_league
    ON storylines(league_id, season, status);
CREATE INDEX IF NOT EXISTS idx_storylines_importance
    ON storylines(league_id, season, importance);

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

CREATE TABLE IF NOT EXISTS storyline_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    storyline_id TEXT NOT NULL,
    league_id TEXT NOT NULL,
    season TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL,
    week INTEGER NOT NULL,
    snapshot_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_storyline
    ON storyline_history(league_id, season, storyline_id, week);

CREATE TABLE IF NOT EXISTS persisted_facts (
    storyline_id TEXT NOT NULL,
    week_recorded INTEGER NOT NULL,
    fact_id TEXT NOT NULL,
    league_id TEXT NOT NULL,
    season TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    data_refs TEXT,
    numbers TEXT,
    category TEXT NOT NULL DEFAULT 'general',
    created_at TEXT NOT NULL,
    PRIMARY KEY (league_id, season, storyline_id, week_recorded, fact_id)
);
CREATE INDEX IF NOT EXISTS idx_facts_storyline
    ON persisted_facts(league_id, season, storyline_id);

CREATE TABLE IF NOT EXISTS story_events (
    id TEXT NOT NULL,
    league_id TEXT NOT NULL,
    season TEXT NOT NULL,
    week INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 1,
    confidence TEXT NOT NULL DEFAULT 'needs_verification',
    source_refs_json TEXT,
    numbers_json TEXT,
    transaction_id TEXT,
    matchup_id TEXT,
    last_accessed_week INTEGER,
    last_accessed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (league_id, season, id)
);
CREATE INDEX IF NOT EXISTS idx_story_events_week
    ON story_events(league_id, season, week, event_type);
CREATE INDEX IF NOT EXISTS idx_story_events_transaction
    ON story_events(league_id, season, transaction_id);
CREATE INDEX IF NOT EXISTS idx_story_events_matchup
    ON story_events(league_id, season, matchup_id);

CREATE TABLE IF NOT EXISTS story_event_entities (
    league_id TEXT NOT NULL,
    season TEXT NOT NULL,
    event_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (league_id, season, event_id, entity_type, entity_id, role)
);
CREATE INDEX IF NOT EXISTS idx_story_event_entities_lookup
    ON story_event_entities(league_id, season, entity_type, entity_id);

CREATE TABLE IF NOT EXISTS storyline_event_links (
    league_id TEXT NOT NULL,
    season TEXT NOT NULL,
    storyline_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    link_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (league_id, season, storyline_id, event_id, link_type)
);
CREATE INDEX IF NOT EXISTS idx_storyline_event_links_event
    ON storyline_event_links(league_id, season, event_id);

CREATE TABLE IF NOT EXISTS storyline_triggers (
    id TEXT NOT NULL,
    league_id TEXT NOT NULL,
    season TEXT NOT NULL,
    storyline_id TEXT,
    event_id TEXT,
    trigger_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    target_week INTEGER,
    condition_json TEXT,
    fire_policy TEXT NOT NULL DEFAULT 'one_shot',
    fired_week INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (league_id, season, id)
);
CREATE INDEX IF NOT EXISTS idx_storyline_triggers_status
    ON storyline_triggers(league_id, season, status, target_week);
CREATE INDEX IF NOT EXISTS idx_storyline_triggers_storyline
    ON storyline_triggers(league_id, season, storyline_id);

CREATE VIRTUAL TABLE IF NOT EXISTS story_memory_fts USING fts5(
    owner_type UNINDEXED,
    owner_id UNINDEXED,
    league_id UNINDEXED,
    season UNINDEXED,
    headline,
    summary,
    tags,
    entity_text,
    trigger_text
);

CREATE TABLE IF NOT EXISTS memory_accesses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id TEXT NOT NULL,
    season TEXT NOT NULL,
    week INTEGER NOT NULL,
    owner_type TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    usage TEXT NOT NULL,
    linked_storyline_id TEXT,
    fact_links_json TEXT,
    reason TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_accesses_owner
    ON memory_accesses(league_id, season, owner_type, owner_id);
CREATE INDEX IF NOT EXISTS idx_memory_accesses_usage
    ON memory_accesses(league_id, season, usage, week);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ContextStore:
    """File-backed SQLite store for persistent agent context.

    Each instance is scoped to a league_id + season pair. The underlying
    database file can hold data for multiple leagues/seasons.
    """

    def __init__(self, db_path: str | Path, league_id: str, season: str) -> None:
        self.db_path = Path(db_path)
        self.league_id = league_id
        self.season = season

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        """Ensure schema is up to date."""
        cur = self._conn.cursor()

        # Check if context_meta exists
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='context_meta'"
        )
        if not cur.fetchone():
            # Fresh database — create everything
            self._conn.executescript(_DDL)
            cur.execute(
                "INSERT INTO context_meta (key, value) VALUES ('schema_version', ?)",
                (SCHEMA_VERSION,),
            )
            self._conn.commit()
            return

        cur.execute("SELECT value FROM context_meta WHERE key = 'schema_version'")
        row = cur.fetchone()
        current = row["value"] if row else "0"

        if current == SCHEMA_VERSION:
            return

        if current == "2.1":
            self._migrate_21_to_3()
            return

        if current != SCHEMA_VERSION:
            raise RuntimeError(
                "Unsupported reporter memory schema version "
                f"{current!r}; expected {SCHEMA_VERSION!r}. "
                "Only schema '2.1' can be migrated automatically."
            )

    def _migrate_21_to_3(self) -> None:
        """Migrate schema 2.1 to schema 3 in place."""
        self._add_storyline_column_if_missing("arc_type", "TEXT")
        self._add_storyline_column_if_missing("importance", "INTEGER")
        self._add_storyline_column_if_missing("origin_week", "INTEGER")
        self._add_storyline_column_if_missing("future_callback_condition", "TEXT")
        self._add_storyline_column_if_missing("last_accessed_week", "INTEGER")
        self._add_storyline_column_if_missing("last_accessed_at", "TEXT")

        self._conn.execute(
            """UPDATE storylines
               SET importance = COALESCE(importance, 6 - priority),
                   origin_week = COALESCE(origin_week, week_created)"""
        )
        self._conn.executescript(_DDL)
        self._rebuild_story_memory_fts()
        self._conn.execute(
            """INSERT INTO context_meta (key, value) VALUES ('schema_version', ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (SCHEMA_VERSION,),
        )
        self._conn.commit()

    def _add_storyline_column_if_missing(
        self, column_name: str, column_definition: str
    ) -> None:
        if column_name in self._column_names("storylines"):
            return
        self._conn.execute(
            f"ALTER TABLE storylines ADD COLUMN {column_name} {column_definition}"
        )

    def _column_names(self, table_name: str) -> set[str]:
        cur = self._conn.execute(f"PRAGMA table_info({table_name})")
        return {row["name"] for row in cur.fetchall()}

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_active_storylines(self) -> list[dict[str, Any]]:
        """All storylines with status='active' for this league+season."""
        cur = self._conn.execute(
            """SELECT * FROM storylines
               WHERE league_id = ? AND season = ? AND status = 'active'
               ORDER BY priority, week_last_updated DESC""",
            (self.league_id, self.season),
        )
        return [self._storyline_row_to_dict(row) for row in cur.fetchall()]

    def get_storylines(self, include_resolved: bool = False) -> list[dict[str, Any]]:
        """Get storylines, optionally including resolved ones."""
        if include_resolved:
            cur = self._conn.execute(
                """SELECT * FROM storylines
                   WHERE league_id = ? AND season = ?
                   ORDER BY priority, week_last_updated DESC""",
                (self.league_id, self.season),
            )
        else:
            cur = self._conn.execute(
                """SELECT * FROM storylines
                   WHERE league_id = ? AND season = ? AND status IN ('active', 'stale')
                   ORDER BY priority, week_last_updated DESC""",
                (self.league_id, self.season),
            )
        return [self._storyline_row_to_dict(row) for row in cur.fetchall()]

    def get_team_context(self, roster_id: int) -> dict[str, Any] | None:
        """Team context note for a specific team."""
        cur = self._conn.execute(
            """SELECT * FROM team_context
               WHERE league_id = ? AND season = ? AND roster_id = ?""",
            (self.league_id, self.season, roster_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)

    def get_all_team_context(self) -> list[dict[str, Any]]:
        """All team context notes for this league+season."""
        cur = self._conn.execute(
            """SELECT * FROM team_context
               WHERE league_id = ? AND season = ?
               ORDER BY roster_id""",
            (self.league_id, self.season),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_league_context(self) -> dict[str, str]:
        """All league context key-value pairs."""
        cur = self._conn.execute(
            """SELECT key, value FROM league_context
               WHERE league_id = ? AND season = ?""",
            (self.league_id, self.season),
        )
        return {row["key"]: row["value"] for row in cur.fetchall()}

    def get_full_context(self) -> dict[str, Any]:
        """Combined context — what the agent reads at the start of research."""
        return {
            "storylines": self.get_active_storylines(),
            "team_context": self.get_all_team_context(),
            "league_context": self.get_league_context(),
        }

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert_storyline(self, storyline: dict[str, Any], *, week: int) -> None:
        """Create or update a storyline by id.

        On update, the previous state is automatically snapshotted to
        storyline_history before overwriting.

        Args:
            storyline: Dict with at least 'id', 'headline', 'summary', 'status'.
                Optional: 'priority', 'tags', 'team_ids'.
            week: Current week number.
        """
        existing = self._conn.execute(
            """SELECT id, arc_type, importance, origin_week,
                      future_callback_condition, last_accessed_week, last_accessed_at
               FROM storylines
               WHERE league_id = ? AND season = ? AND id = ?""",
            (self.league_id, self.season, storyline["id"]),
        ).fetchone()
        if existing:
            self._append_storyline_history(storyline["id"], week=week)

        now = _now_iso()
        priority = storyline.get("priority", 2)
        importance = storyline.get(
            "importance", existing["importance"] if existing else 6 - priority
        )
        origin_week = storyline.get(
            "origin_week", existing["origin_week"] if existing else week
        )
        arc_type = storyline.get("arc_type", existing["arc_type"] if existing else None)
        future_callback_condition = storyline.get(
            "future_callback_condition",
            existing["future_callback_condition"] if existing else None,
        )
        last_accessed_week = storyline.get(
            "last_accessed_week",
            existing["last_accessed_week"] if existing else None,
        )
        last_accessed_at = storyline.get(
            "last_accessed_at",
            existing["last_accessed_at"] if existing else None,
        )
        tags = json.dumps(storyline.get("tags", [])) if storyline.get("tags") else None
        team_ids = (
            json.dumps(storyline.get("team_ids", []))
            if storyline.get("team_ids")
            else None
        )

        self._conn.execute(
            """INSERT INTO storylines
                   (id, league_id, season, headline, summary, status, priority,
                    arc_type, importance, origin_week, future_callback_condition,
                    tags, team_ids, week_created, week_last_updated,
                    last_accessed_week, last_accessed_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(league_id, season, id) DO UPDATE SET
                   headline = excluded.headline,
                   summary = excluded.summary,
                   status = excluded.status,
                   priority = excluded.priority,
                   arc_type = COALESCE(excluded.arc_type, storylines.arc_type),
                   importance = COALESCE(excluded.importance, storylines.importance),
                   origin_week = COALESCE(excluded.origin_week, storylines.origin_week),
                   future_callback_condition = COALESCE(
                       excluded.future_callback_condition,
                       storylines.future_callback_condition
                   ),
                   tags = excluded.tags,
                   team_ids = excluded.team_ids,
                   week_last_updated = excluded.week_last_updated,
                   last_accessed_week = COALESCE(
                       excluded.last_accessed_week,
                       storylines.last_accessed_week
                   ),
                   last_accessed_at = COALESCE(
                       excluded.last_accessed_at,
                       storylines.last_accessed_at
                   ),
                   updated_at = excluded.updated_at""",
            (
                storyline["id"],
                self.league_id,
                self.season,
                storyline["headline"],
                storyline["summary"],
                storyline.get("status", "active"),
                priority,
                arc_type,
                importance,
                origin_week,
                future_callback_condition,
                tags,
                team_ids,
                week,  # week_created (ignored on update due to ON CONFLICT)
                week,  # week_last_updated
                last_accessed_week,
                last_accessed_at,
                now,  # created_at (ignored on update)
                now,  # updated_at
            ),
        )
        self._sync_storyline_fts(storyline["id"])
        self._conn.commit()

    def resolve_storyline(self, storyline_id: str) -> None:
        """Mark a storyline as resolved."""
        self._conn.execute(
            """UPDATE storylines SET status = 'resolved', updated_at = ?
               WHERE id = ? AND league_id = ? AND season = ?""",
            (_now_iso(), storyline_id, self.league_id, self.season),
        )
        self._conn.commit()

    def upsert_team_context(
        self,
        roster_id: int,
        narrative: str,
        outlook: str | None = None,
        *,
        week: int,
    ) -> None:
        """Create or replace team context note."""
        self._conn.execute(
            """INSERT INTO team_context
                   (league_id, season, roster_id, narrative, outlook,
                    week_last_updated, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(league_id, season, roster_id) DO UPDATE SET
                   narrative = excluded.narrative,
                   outlook = excluded.outlook,
                   week_last_updated = excluded.week_last_updated,
                   updated_at = excluded.updated_at""",
            (
                self.league_id,
                self.season,
                roster_id,
                narrative,
                outlook,
                week,
                _now_iso(),
            ),
        )
        self._conn.commit()

    def upsert_league_context(self, key: str, value: str, *, week: int) -> None:
        """Create or replace a league context entry."""
        self._conn.execute(
            """INSERT INTO league_context
                   (league_id, season, key, value, week_last_updated, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(league_id, season, key) DO UPDATE SET
                   value = excluded.value,
                   week_last_updated = excluded.week_last_updated,
                   updated_at = excluded.updated_at""",
            (self.league_id, self.season, key, value, week, _now_iso()),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def mark_stale(self, current_week: int, weeks_threshold: int = 4) -> int:
        """Mark storylines as 'stale' if not updated in N weeks.

        Returns count of storylines marked stale.
        """
        cutoff_week = current_week - weeks_threshold
        cur = self._conn.execute(
            """UPDATE storylines SET status = 'stale', updated_at = ?
               WHERE league_id = ? AND season = ? AND status = 'active'
               AND week_last_updated <= ?""",
            (_now_iso(), self.league_id, self.season, cutoff_week),
        )
        self._conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------------
    # Storyline History & Facts
    # ------------------------------------------------------------------

    def _append_storyline_history(self, storyline_id: str, *, week: int) -> None:
        """Snapshot the current state of a storyline into history."""
        row = self._conn.execute(
            """SELECT * FROM storylines
               WHERE league_id = ? AND season = ? AND id = ?""",
            (self.league_id, self.season, storyline_id),
        ).fetchone()
        if not row:
            return
        self._conn.execute(
            """INSERT INTO storyline_history
                   (storyline_id, league_id, season, headline, summary,
                    status, priority, week, snapshot_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row["id"],
                row["league_id"],
                row["season"],
                row["headline"],
                row["summary"],
                row["status"],
                row["priority"],
                week,
                _now_iso(),
            ),
        )

    def get_storyline_summaries(self) -> list[dict[str, Any]]:
        """Lightweight active/stale storyline list for curator input."""
        cur = self._conn.execute(
            """SELECT id, headline, summary, status, tags, team_ids,
                      priority, arc_type, importance, origin_week,
                      future_callback_condition, week_created, week_last_updated,
                      last_accessed_week, last_accessed_at
               FROM storylines
               WHERE league_id = ? AND season = ? AND status IN ('active', 'stale')
               ORDER BY priority, week_last_updated DESC""",
            (self.league_id, self.season),
        )
        rows = []
        for row in cur.fetchall():
            rows.append(self._storyline_row_to_dict(row))
        return rows

    def get_storyline_history(self, storyline_id: str) -> list[dict[str, Any]]:
        """Full history for one storyline, ordered by week ASC."""
        cur = self._conn.execute(
            """SELECT * FROM storyline_history
               WHERE league_id = ? AND season = ? AND storyline_id = ?
               ORDER BY week ASC, id ASC""",
            (self.league_id, self.season, storyline_id),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_storyline_facts(self, storyline_id: str) -> list[dict[str, Any]]:
        """All persisted facts for one storyline, ordered by week_recorded ASC."""
        cur = self._conn.execute(
            """SELECT * FROM persisted_facts
               WHERE league_id = ? AND season = ? AND storyline_id = ?
               ORDER BY week_recorded ASC""",
            (self.league_id, self.season, storyline_id),
        )
        rows = []
        for row in cur.fetchall():
            d = dict(row)
            d["data_refs"] = json.loads(d["data_refs"]) if d.get("data_refs") else []
            d["numbers"] = json.loads(d["numbers"]) if d.get("numbers") else {}
            rows.append(d)
        return rows

    def get_enriched_storylines(self, storyline_ids: list[str]) -> list[dict[str, Any]]:
        """Current state + history + facts for a list of storyline IDs.

        Each dict includes 'history' (capped at 6 most recent) and
        'facts' (capped at 15 most recent).
        """
        if not storyline_ids:
            return []
        placeholders = ",".join("?" for _ in storyline_ids)
        cur = self._conn.execute(
            f"""SELECT * FROM storylines
                WHERE league_id = ? AND season = ? AND id IN ({placeholders})
                ORDER BY priority, week_last_updated DESC""",
            [self.league_id, self.season, *storyline_ids],
        )
        results = []
        for row in cur.fetchall():
            d = self._storyline_row_to_dict(row)
            history = self.get_storyline_history(d["id"])
            d["history"] = history[-6:]
            facts = self.get_storyline_facts(d["id"])
            d["facts"] = facts[-15:]
            results.append(d)
        return results

    def persist_facts(
        self, facts: list[dict[str, Any]], storyline_id: str, *, week: int
    ) -> int:
        """Persist facts linked to a storyline.

        Uses INSERT OR IGNORE to deduplicate on (storyline_id, week, fact_id).
        Returns count of newly inserted facts.
        """
        now = _now_iso()
        inserted = 0
        for fact in facts:
            data_refs = json.dumps(fact.get("data_refs", []))
            numbers = json.dumps(fact.get("numbers", {}))
            cur = self._conn.execute(
                """INSERT OR IGNORE INTO persisted_facts
                       (storyline_id, week_recorded, fact_id, league_id, season,
                        claim_text, data_refs, numbers, category, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    storyline_id,
                    week,
                    fact["id"],
                    self.league_id,
                    self.season,
                    fact["claim_text"],
                    data_refs,
                    numbers,
                    fact.get("category", "general"),
                    now,
                ),
            )
            inserted += cur.rowcount
        self._conn.commit()
        return inserted

    # ------------------------------------------------------------------
    # Story Events, Triggers, Accesses, and FTS
    # ------------------------------------------------------------------

    def upsert_story_event(self, event: dict[str, Any]) -> None:
        """Create or update source-backed event evidence."""
        source_refs = event.get("source_refs", event.get("source_refs_json", []))
        confidence = event.get("confidence", "needs_verification")
        if confidence == "verified" and not source_refs:
            raise ValueError("verified story events require at least one source ref")

        now = _now_iso()
        self._conn.execute(
            """INSERT INTO story_events
                   (id, league_id, season, week, event_type, headline, summary,
                    importance, confidence, source_refs_json, numbers_json,
                    transaction_id, matchup_id, last_accessed_week, last_accessed_at,
                    created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(league_id, season, id) DO UPDATE SET
                   week = excluded.week,
                   event_type = excluded.event_type,
                   headline = excluded.headline,
                   summary = excluded.summary,
                   importance = excluded.importance,
                   confidence = excluded.confidence,
                   source_refs_json = excluded.source_refs_json,
                   numbers_json = excluded.numbers_json,
                   transaction_id = excluded.transaction_id,
                   matchup_id = excluded.matchup_id,
                   last_accessed_week = COALESCE(
                       excluded.last_accessed_week,
                       story_events.last_accessed_week
                   ),
                   last_accessed_at = COALESCE(
                       excluded.last_accessed_at,
                       story_events.last_accessed_at
                   ),
                   updated_at = excluded.updated_at""",
            (
                event["id"],
                self.league_id,
                self.season,
                event["week"],
                event["event_type"],
                event["headline"],
                event["summary"],
                event.get("importance", 1),
                confidence,
                self._json_text(source_refs, []),
                self._json_text(event.get("numbers", event.get("numbers_json", {})), {}),
                event.get("transaction_id"),
                event.get("matchup_id"),
                event.get("last_accessed_week"),
                event.get("last_accessed_at"),
                now,
                now,
            ),
        )
        self._sync_event_fts(event["id"])
        self._conn.commit()

    def replace_story_event_entities(
        self, event_id: str, entities: list[dict[str, Any]]
    ) -> None:
        """Replace normalized entity links for one story event."""
        self._conn.execute(
            """DELETE FROM story_event_entities
               WHERE league_id = ? AND season = ? AND event_id = ?""",
            (self.league_id, self.season, event_id),
        )

        now = _now_iso()
        for entity in entities:
            entity_type = entity.get("entity_type", entity.get("type"))
            if not entity_type:
                raise ValueError("story event entities require entity_type")
            display_name = entity.get("display_name", entity.get("name"))
            entity_id = entity.get("entity_id", entity.get("id", display_name))
            if not entity_id:
                raise ValueError("story event entities require entity_id or display_name")

            self._conn.execute(
                """INSERT INTO story_event_entities
                       (league_id, season, event_id, entity_type, entity_id,
                        display_name, role, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    self.league_id,
                    self.season,
                    event_id,
                    entity_type,
                    str(entity_id),
                    display_name,
                    entity.get("role", ""),
                    now,
                ),
            )

        self._sync_event_fts(event_id)
        self._conn.commit()

    def link_storyline_event(
        self, storyline_id: str, event_id: str, link_type: str
    ) -> None:
        """Link a narrative storyline card to source-backed event evidence."""
        self._conn.execute(
            """INSERT OR IGNORE INTO storyline_event_links
                   (league_id, season, storyline_id, event_id, link_type, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (self.league_id, self.season, storyline_id, event_id, link_type, _now_iso()),
        )
        self._conn.commit()

    def upsert_storyline_trigger(self, trigger: dict[str, Any]) -> None:
        """Create or update a dormant callback trigger."""
        now = _now_iso()
        condition = trigger.get("condition", trigger.get("condition_json", {}))
        self._conn.execute(
            """INSERT INTO storyline_triggers
                   (id, league_id, season, storyline_id, event_id, trigger_type,
                    status, target_week, condition_json, fire_policy, fired_week,
                    created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(league_id, season, id) DO UPDATE SET
                   storyline_id = excluded.storyline_id,
                   event_id = excluded.event_id,
                   trigger_type = excluded.trigger_type,
                   status = excluded.status,
                   target_week = excluded.target_week,
                   condition_json = excluded.condition_json,
                   fire_policy = excluded.fire_policy,
                   fired_week = excluded.fired_week,
                   updated_at = excluded.updated_at""",
            (
                trigger["id"],
                self.league_id,
                self.season,
                trigger.get("storyline_id"),
                trigger.get("event_id"),
                trigger["trigger_type"],
                trigger.get("status", "open"),
                trigger.get("target_week"),
                self._json_text(condition, {}),
                trigger.get("fire_policy", "one_shot"),
                trigger.get("fired_week"),
                now,
                now,
            ),
        )
        self._sync_trigger_fts(trigger["id"])
        self._conn.commit()

    def record_memory_access(
        self,
        *,
        owner_type: str,
        owner_id: str,
        week: int,
        usage: str,
        linked_storyline_id: str | None = None,
        fact_links: list[str] | None = None,
        reason: str | None = None,
    ) -> int:
        """Record retrieval/usage feedback for a memory candidate."""
        now = _now_iso()
        cur = self._conn.execute(
            """INSERT INTO memory_accesses
                   (league_id, season, week, owner_type, owner_id, usage,
                    linked_storyline_id, fact_links_json, reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                self.league_id,
                self.season,
                week,
                owner_type,
                owner_id,
                usage,
                linked_storyline_id,
                self._json_text(fact_links or [], []),
                reason,
                now,
            ),
        )

        if owner_type == "storyline":
            self._conn.execute(
                """UPDATE storylines
                   SET last_accessed_week = ?, last_accessed_at = ?
                   WHERE league_id = ? AND season = ? AND id = ?""",
                (week, now, self.league_id, self.season, owner_id),
            )
        elif owner_type in {"event", "story_event"}:
            self._conn.execute(
                """UPDATE story_events
                   SET last_accessed_week = ?, last_accessed_at = ?
                   WHERE league_id = ? AND season = ? AND id = ?""",
                (week, now, self.league_id, self.season, owner_id),
            )

        self._conn.commit()
        return int(cur.lastrowid)

    def get_story_event(self, event_id: str) -> dict[str, Any] | None:
        """Return one story event with parsed JSON fields, or None."""
        row = self._conn.execute(
            """SELECT * FROM story_events
               WHERE league_id = ? AND season = ? AND id = ?""",
            (self.league_id, self.season, event_id),
        ).fetchone()
        if not row:
            return None
        return self._event_row_to_dict(row)

    def get_story_event_entities(self, event_id: str) -> list[dict[str, Any]]:
        """Return normalized entity links for one story event."""
        cur = self._conn.execute(
            """SELECT entity_type, entity_id, display_name, role
               FROM story_event_entities
               WHERE league_id = ? AND season = ? AND event_id = ?
               ORDER BY entity_type, role, entity_id""",
            (self.league_id, self.season, event_id),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_storyline_events(self, storyline_id: str) -> list[dict[str, Any]]:
        """Return events linked to a storyline, including link_type."""
        cur = self._conn.execute(
            """SELECT e.*, l.link_type
               FROM storyline_event_links l
               JOIN story_events e
                 ON e.league_id = l.league_id
                AND e.season = l.season
                AND e.id = l.event_id
               WHERE l.league_id = ? AND l.season = ? AND l.storyline_id = ?
               ORDER BY e.week ASC, e.id ASC""",
            (self.league_id, self.season, storyline_id),
        )
        results = []
        for row in cur.fetchall():
            event = self._event_row_to_dict(row)
            event["link_type"] = row["link_type"]
            event["entities"] = self.get_story_event_entities(event["id"])
            results.append(event)
        return results

    def get_storyline_triggers(
        self,
        storyline_id: str | None = None,
        *,
        status: str | None = "open",
    ) -> list[dict[str, Any]]:
        """Return triggers, optionally filtered by storyline and status."""
        clauses = ["league_id = ?", "season = ?"]
        params: list[Any] = [self.league_id, self.season]
        if storyline_id is not None:
            clauses.append("storyline_id = ?")
            params.append(storyline_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        cur = self._conn.execute(
            f"""SELECT * FROM storyline_triggers
                WHERE {' AND '.join(clauses)}
                ORDER BY target_week ASC NULLS LAST, id ASC""",
            params,
        )
        return [self._trigger_row_to_dict(row) for row in cur.fetchall()]

    def get_trigger(self, trigger_id: str) -> dict[str, Any] | None:
        """Return one trigger by id, or None."""
        row = self._conn.execute(
            """SELECT * FROM storyline_triggers
               WHERE league_id = ? AND season = ? AND id = ?""",
            (self.league_id, self.season, trigger_id),
        ).fetchone()
        if not row:
            return None
        return self._trigger_row_to_dict(row)

    def update_trigger_status(
        self,
        trigger_id: str,
        *,
        status: str,
        fired_week: int | None = None,
    ) -> bool:
        """Update trigger status; returns True if a row was updated."""
        cur = self._conn.execute(
            """UPDATE storyline_triggers
               SET status = ?,
                   fired_week = COALESCE(?, fired_week),
                   updated_at = ?
               WHERE league_id = ? AND season = ? AND id = ?""",
            (
                status,
                fired_week,
                _now_iso(),
                self.league_id,
                self.season,
                trigger_id,
            ),
        )
        self._conn.commit()
        if cur.rowcount:
            self._sync_trigger_fts(trigger_id)
            self._conn.commit()
        return cur.rowcount > 0

    def storyline_ids_for_event(self, event_id: str) -> list[str]:
        """Return storyline IDs linked to an event."""
        cur = self._conn.execute(
            """SELECT storyline_id FROM storyline_event_links
               WHERE league_id = ? AND season = ? AND event_id = ?
               ORDER BY storyline_id""",
            (self.league_id, self.season, event_id),
        )
        return [row["storyline_id"] for row in cur.fetchall()]

    def find_event_entities(
        self, entity_type: str, entity_id: str
    ) -> list[dict[str, Any]]:
        """Return entity rows for events matching one entity key."""
        cur = self._conn.execute(
            """SELECT event_id, entity_type, entity_id, display_name, role
               FROM story_event_entities
               WHERE league_id = ? AND season = ?
                 AND entity_type = ? AND entity_id = ?""",
            (self.league_id, self.season, entity_type, str(entity_id)),
        )
        return [dict(row) for row in cur.fetchall()]

    def find_event_ids_by_transaction_ids(
        self, transaction_ids: set[str] | list[str]
    ) -> list[str]:
        """Return event IDs with matching transaction_id values."""
        ids = [str(value) for value in transaction_ids]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        cur = self._conn.execute(
            f"""SELECT id FROM story_events
                WHERE league_id = ? AND season = ?
                  AND transaction_id IN ({placeholders})
                ORDER BY id""",
            [self.league_id, self.season, *ids],
        )
        return [row["id"] for row in cur.fetchall()]

    def find_event_ids_by_matchup_ids(
        self, matchup_ids: set[str] | list[str]
    ) -> list[str]:
        """Return event IDs with matching matchup_id values."""
        ids = [str(value) for value in matchup_ids]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        cur = self._conn.execute(
            f"""SELECT id FROM story_events
                WHERE league_id = ? AND season = ?
                  AND matchup_id IN ({placeholders})
                ORDER BY id""",
            [self.league_id, self.season, *ids],
        )
        return [row["id"] for row in cur.fetchall()]

    def find_storyline_ids_by_team_id(self, team_id: int) -> list[str]:
        """Return storyline IDs whose team_ids JSON includes team_id."""
        cur = self._conn.execute(
            """SELECT id, team_ids FROM storylines
               WHERE league_id = ? AND season = ?
               ORDER BY id""",
            (self.league_id, self.season),
        )
        matches: list[str] = []
        for row in cur.fetchall():
            team_ids = json.loads(row["team_ids"]) if row["team_ids"] else []
            if team_id in team_ids:
                matches.append(row["id"])
        return matches

    def get_storyline(self, storyline_id: str) -> dict[str, Any] | None:
        """Return one storyline dict, or None."""
        row = self._conn.execute(
            """SELECT * FROM storylines
               WHERE league_id = ? AND season = ? AND id = ?""",
            (self.league_id, self.season, storyline_id),
        ).fetchone()
        if not row:
            return None
        return self._storyline_row_to_dict(row)

    def search_memory_fts(
        self, match_query: str, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Run an FTS5 MATCH against story_memory_fts.

        Returns rows with owner_type, owner_id, and bm25 rank (lower is better).
        """
        if not match_query.strip():
            return []
        try:
            cur = self._conn.execute(
                """SELECT owner_type, owner_id,
                          bm25(story_memory_fts) AS rank
                   FROM story_memory_fts
                   WHERE story_memory_fts MATCH ?
                     AND league_id = ? AND season = ?
                   ORDER BY rank
                   LIMIT ?""",
                (match_query, self.league_id, self.season, limit),
            )
        except sqlite3.OperationalError:
            return []
        return [dict(row) for row in cur.fetchall()]

    def rebuild_story_memory_fts(self) -> None:
        """Rebuild FTS rows for all storylines, events, and triggers in scope."""
        self._rebuild_story_memory_fts()
        self._conn.commit()

    def _rebuild_story_memory_fts(self) -> None:
        self._conn.execute(
            """DELETE FROM story_memory_fts
               WHERE league_id = ? AND season = ?""",
            (self.league_id, self.season),
        )

        storyline_ids = self._scoped_ids("storylines")
        for storyline_id in storyline_ids:
            self._sync_storyline_fts(storyline_id)

        event_ids = self._scoped_ids("story_events")
        for event_id in event_ids:
            self._sync_event_fts(event_id)

        trigger_ids = self._scoped_ids("storyline_triggers")
        for trigger_id in trigger_ids:
            self._sync_trigger_fts(trigger_id)

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _event_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["source_refs"] = (
            json.loads(d["source_refs_json"]) if d.get("source_refs_json") else []
        )
        d["numbers"] = json.loads(d["numbers_json"]) if d.get("numbers_json") else {}
        d.pop("source_refs_json", None)
        d.pop("numbers_json", None)
        return d

    @staticmethod
    def _trigger_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["condition"] = (
            json.loads(d["condition_json"]) if d.get("condition_json") else {}
        )
        d.pop("condition_json", None)
        return d

    @staticmethod
    def _storyline_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        if d.get("tags"):
            d["tags"] = json.loads(d["tags"])
        else:
            d["tags"] = []
        if d.get("team_ids"):
            d["team_ids"] = json.loads(d["team_ids"])
        else:
            d["team_ids"] = []
        d.setdefault("arc_type", None)
        if d.get("importance") is None:
            d["importance"] = 6 - d.get("priority", 2)
        if d.get("origin_week") is None:
            d["origin_week"] = d.get("week_created")
        d.setdefault("future_callback_condition", None)
        d.setdefault("last_accessed_week", None)
        d.setdefault("last_accessed_at", None)
        return d

    def _sync_storyline_fts(self, storyline_id: str) -> None:
        self._delete_fts_row("storyline", storyline_id)
        row = self._conn.execute(
            """SELECT * FROM storylines
               WHERE league_id = ? AND season = ? AND id = ?""",
            (self.league_id, self.season, storyline_id),
        ).fetchone()
        if not row:
            return

        storyline = self._storyline_row_to_dict(row)
        self._insert_fts_row(
            owner_type="storyline",
            owner_id=storyline_id,
            headline=storyline["headline"],
            summary=storyline["summary"],
            tags=" ".join(storyline["tags"] + [storyline.get("arc_type") or ""]),
            entity_text=" ".join(str(team_id) for team_id in storyline["team_ids"]),
            trigger_text=storyline.get("future_callback_condition") or "",
        )

    def _sync_event_fts(self, event_id: str) -> None:
        self._delete_fts_row("event", event_id)
        row = self._conn.execute(
            """SELECT * FROM story_events
               WHERE league_id = ? AND season = ? AND id = ?""",
            (self.league_id, self.season, event_id),
        ).fetchone()
        if not row:
            return

        entity_rows = self._conn.execute(
            """SELECT entity_type, entity_id, display_name, role
               FROM story_event_entities
               WHERE league_id = ? AND season = ? AND event_id = ?
               ORDER BY entity_type, role, entity_id""",
            (self.league_id, self.season, event_id),
        ).fetchall()
        entity_text = " ".join(
            " ".join(
                str(value)
                for value in [
                    entity["entity_type"],
                    entity["entity_id"],
                    entity["display_name"],
                    entity["role"],
                ]
                if value
            )
            for entity in entity_rows
        )
        self._insert_fts_row(
            owner_type="event",
            owner_id=event_id,
            headline=row["headline"],
            summary=row["summary"],
            tags=" ".join([row["event_type"], row["confidence"]]),
            entity_text=entity_text,
            trigger_text="",
        )

    def _sync_trigger_fts(self, trigger_id: str) -> None:
        self._delete_fts_row("trigger", trigger_id)
        row = self._conn.execute(
            """SELECT * FROM storyline_triggers
               WHERE league_id = ? AND season = ? AND id = ?""",
            (self.league_id, self.season, trigger_id),
        ).fetchone()
        if not row:
            return

        trigger_text = " ".join(
            str(value)
            for value in [
                row["trigger_type"],
                row["status"],
                row["target_week"],
                row["condition_json"],
                row["fire_policy"],
                row["fired_week"],
            ]
            if value is not None
        )
        entity_text = " ".join(
            str(value)
            for value in [row["storyline_id"], row["event_id"]]
            if value
        )
        self._insert_fts_row(
            owner_type="trigger",
            owner_id=trigger_id,
            headline=row["trigger_type"],
            summary=row["condition_json"] or "",
            tags=row["status"],
            entity_text=entity_text,
            trigger_text=trigger_text,
        )

    def _delete_fts_row(self, owner_type: str, owner_id: str) -> None:
        self._conn.execute(
            """DELETE FROM story_memory_fts
               WHERE owner_type = ? AND owner_id = ?
               AND league_id = ? AND season = ?""",
            (owner_type, owner_id, self.league_id, self.season),
        )

    def _insert_fts_row(
        self,
        *,
        owner_type: str,
        owner_id: str,
        headline: str,
        summary: str,
        tags: str,
        entity_text: str,
        trigger_text: str,
    ) -> None:
        self._conn.execute(
            """INSERT INTO story_memory_fts
                   (owner_type, owner_id, league_id, season, headline, summary,
                    tags, entity_text, trigger_text)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                owner_type,
                owner_id,
                self.league_id,
                self.season,
                headline,
                summary,
                tags,
                entity_text,
                trigger_text,
            ),
        )

    def _scoped_ids(self, table_name: str) -> list[str]:
        cur = self._conn.execute(
            f"""SELECT id FROM {table_name}
                WHERE league_id = ? AND season = ?
                ORDER BY id""",
            (self.league_id, self.season),
        )
        return [row["id"] for row in cur.fetchall()]

    @staticmethod
    def _json_text(value: Any, default: Any) -> str:
        if value is None:
            value = default
        if isinstance(value, str):
            return value
        return json.dumps(value)
