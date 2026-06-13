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


SCHEMA_VERSION = "2.1"

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
    tags TEXT,
    team_ids TEXT,
    week_created INTEGER NOT NULL,
    week_last_updated INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (league_id, season, id)
);
CREATE INDEX IF NOT EXISTS idx_storylines_league
    ON storylines(league_id, season, status);

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

        if current != SCHEMA_VERSION:
            raise RuntimeError(
                "Unsupported reporter memory schema version "
                f"{current!r}; expected {SCHEMA_VERSION!r}. "
                "Delete or recreate the context database."
            )

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
            """SELECT id FROM storylines
               WHERE league_id = ? AND season = ? AND id = ?""",
            (self.league_id, self.season, storyline["id"]),
        ).fetchone()
        if existing:
            self._append_storyline_history(storyline["id"], week=week)

        now = _now_iso()
        tags = json.dumps(storyline.get("tags", [])) if storyline.get("tags") else None
        team_ids = (
            json.dumps(storyline.get("team_ids", []))
            if storyline.get("team_ids")
            else None
        )

        self._conn.execute(
            """INSERT INTO storylines
                   (id, league_id, season, headline, summary, status, priority,
                    tags, team_ids, week_created, week_last_updated, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(league_id, season, id) DO UPDATE SET
                   headline = excluded.headline,
                   summary = excluded.summary,
                   status = excluded.status,
                   priority = excluded.priority,
                   tags = excluded.tags,
                   team_ids = excluded.team_ids,
                   week_last_updated = excluded.week_last_updated,
                   updated_at = excluded.updated_at""",
            (
                storyline["id"],
                self.league_id,
                self.season,
                storyline["headline"],
                storyline["summary"],
                storyline.get("status", "active"),
                storyline.get("priority", 2),
                tags,
                team_ids,
                week,  # week_created (ignored on update due to ON CONFLICT)
                week,  # week_last_updated
                now,  # created_at (ignored on update)
                now,  # updated_at
            ),
        )
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
                      priority, week_created, week_last_updated
               FROM storylines
               WHERE league_id = ? AND season = ? AND status IN ('active', 'stale')
               ORDER BY priority, week_last_updated DESC""",
            (self.league_id, self.season),
        )
        rows = []
        for row in cur.fetchall():
            d = dict(row)
            d["tags"] = json.loads(d["tags"]) if d.get("tags") else []
            d["team_ids"] = json.loads(d["team_ids"]) if d.get("team_ids") else []
            rows.append(d)
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

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
        return d
