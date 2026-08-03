"""Storyline callback triggers."""

from __future__ import annotations

from typing import Any

from reporter_memory.store.serializers import _now_iso


class TriggersMixin:
    """Dormant callback trigger CRUD and status updates."""

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
