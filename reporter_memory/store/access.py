"""Memory access / usage recording."""

from __future__ import annotations

from reporter_memory.store.serializers import _now_iso


class AccessMixin:
    """Durable retrieval and usage feedback trail."""

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
