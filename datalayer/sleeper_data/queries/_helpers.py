"""Shared utility functions for query modules."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

# Position order for sorting (standard fantasy football order)
POSITION_ORDER = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "K": 4, "DEF": 5}
POSITIONS = ["qb", "rb", "wr", "te", "k", "def"]

# Fields to exclude from team profile responses (internal/UI-only)
_TEAM_PROFILE_EXCLUDE = {"avatar_url"}


def fetch_all(conn, sql: str, params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Execute SQL and return all rows as list of dicts."""
    cur = conn.execute(sql, params or {})
    columns = [col[0] for col in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def fetch_one(conn, sql: str, params: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """Execute SQL and return first row as dict, or None."""
    cur = conn.execute(sql, params or {})
    row = cur.fetchone()
    if not row:
        return None
    columns = [col[0] for col in cur.description]
    return dict(zip(columns, row))


def normalize_lookup_key(value: Any) -> str:
    """Normalize a lookup key to a stripped string."""
    if value is None:
        return ""
    return str(value).strip()


def _strip_id_fields_recursive(value: Any) -> Any:
    """Recursively remove fields ending with '_id' from dicts."""
    if isinstance(value, dict):
        return {
            key: _strip_id_fields_recursive(val)
            for key, val in value.items()
            if not key.endswith("_id")
        }
    if isinstance(value, list):
        return [_strip_id_fields_recursive(item) for item in value]
    return value


def strip_id_fields(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Remove all '_id' fields from a dict."""
    if payload is None:
        return None
    return _strip_id_fields_recursive(payload)


def strip_id_fields_list(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove all '_id' fields from a list of dicts."""
    return [_strip_id_fields_recursive(item) for item in items]


def clean_team_profile(profile: dict[str, Any] | None) -> dict[str, Any] | None:
    """Remove ID fields and UI-only fields (like avatar_url) from team profile."""
    if profile is None:
        return None
    return {
        key: value
        for key, value in profile.items()
        if not key.endswith("_id") and key not in _TEAM_PROFILE_EXCLUDE
    }


def format_record(wins: int | None, losses: int | None, ties: int | None) -> str | None:
    """Format W-L-T record as string (e.g., '7-3' or '7-3-1')."""
    if wins is None or losses is None:
        return None
    ties = ties or 0
    if ties:
        return f"{wins}-{losses}-{ties}"
    return f"{wins}-{losses}"


def organize_players_by_role_and_position(
    players: list[dict[str, Any]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Organize players into a structured dict by role and position.

    Returns:
        {
            "starters": {"qb": [...], "rb": [...], ...},
            "bench": {"qb": [...], "rb": [...], ...}
        }
    """
    result: dict[str, dict[str, list[dict[str, Any]]]] = {
        "starters": {pos: [] for pos in POSITIONS},
        "bench": {pos: [] for pos in POSITIONS},
    }

    for player in players:
        role = player.get("role", "bench")
        position = (player.get("position") or "").upper()
        pos_key = position.lower() if position in POSITION_ORDER else "def"

        if role == "starter":
            bucket = "starters"
        else:
            bucket = "bench"

        result[bucket][pos_key].append(player)

    # Sort each position group by points descending (if available), then by name
    def sort_key(p: dict[str, Any]) -> tuple[float, str]:
        points = p.get("points")
        return (-(points if points is not None else 0), p.get("player_name") or "")

    for role_bucket in result.values():
        for pos_list in role_bucket.values():
            pos_list.sort(key=sort_key)

    return result
