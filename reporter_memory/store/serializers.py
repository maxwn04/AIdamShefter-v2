"""Row serializers and small shared helpers for ContextStore mixins."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Back-compat alias used inside mixins copied from the monolith.
_now_iso = now_iso


class SerializersMixin:
    """JSON/row helpers mixed into ContextStore."""

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
