"""Story events, entity links, and storyline-event joins."""

from __future__ import annotations

import json
from typing import Any

from reporter_memory.store.serializers import _now_iso


class EventsMixin:
    """Source-backed event evidence graph."""

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
