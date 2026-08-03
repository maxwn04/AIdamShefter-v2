"""Connection lifecycle and schema migration for ContextStore."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from reporter_memory.schema import SCHEMA_VERSION, _DDL
from reporter_memory.store.serializers import SerializersMixin


class StoreBase(SerializersMixin):
    """Owns DB connection, migration, and close."""

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

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
