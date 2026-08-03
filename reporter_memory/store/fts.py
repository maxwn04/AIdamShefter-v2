"""FTS5 index maintenance and search for story memory."""

from __future__ import annotations

import sqlite3
from typing import Any


class FtsMixin:
    """story_memory_fts sync, rebuild, and MATCH queries."""

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
