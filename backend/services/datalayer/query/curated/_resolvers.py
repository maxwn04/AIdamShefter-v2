"""Name/ID resolution functions for flexible lookups."""

from __future__ import annotations

from typing import Any

from ._helpers import fetch_all, fetch_one, normalize_lookup_key


def resolve_player_id(conn, player_key: Any) -> dict[str, Any]:
    """Resolve a player name or ID to a player_id.

    Args:
        conn: SQLite database connection.
        player_key: Player name (str) or player_id.

    Returns:
        On success: {"found": True, "player_id": str, "player_name": str, ...}
        On failure: {"found": False, "player_key": ...}
        On ambiguous: {"found": False, "player_key": ..., "matches": [...]}
    """
    key = normalize_lookup_key(player_key)
    if not key:
        return {"found": False, "player_key": player_key}

    by_id = fetch_one(
        conn,
        """
        SELECT player_id, full_name, position, age, nfl_team
        FROM players
        WHERE player_id = :player_id
        """,
        {"player_id": key},
    )
    if by_id:
        return {
            "found": True,
            "player_id": by_id["player_id"],
            "player_name": by_id["full_name"],
            "position": by_id.get("position"),
            "age": by_id.get("age"),
            "nfl_team": by_id.get("nfl_team"),
        }

    matches = fetch_all(
        conn,
        """
        SELECT player_id, full_name AS player_name, position, age, nfl_team
        FROM players
        WHERE full_name IS NOT NULL AND lower(full_name) = lower(:full_name)
        ORDER BY full_name ASC
        """,
        {"full_name": key},
    )
    if not matches:
        return {"found": False, "player_key": player_key}
    if len(matches) > 1:
        return {"found": False, "player_key": player_key, "matches": matches}
    return {
        "found": True,
        "player_id": matches[0]["player_id"],
        "player_name": matches[0]["player_name"],
    }


def resolve_roster_id(conn, league_id: str, roster_key: Any) -> dict[str, Any]:
    """Resolve a team name, manager name, or roster_id to a roster_id.

    Args:
        conn: SQLite database connection.
        league_id: The league identifier.
        roster_key: Team name, manager name (str), or roster_id (int).

    Returns:
        On success: {"found": True, "roster_id": int, "team_name": str | None}
        On failure: {"found": False, "roster_key": ...}
        On ambiguous: {"found": False, "roster_key": ..., "matches": [...]}
    """
    key = normalize_lookup_key(roster_key)
    if not key:
        return {"found": False, "roster_key": roster_key}

    if key.isdigit():
        roster_id = int(key)
        roster = fetch_one(
            conn,
            """
            SELECT league_id, roster_id
            FROM rosters
            WHERE league_id = :league_id AND roster_id = :roster_id
            """,
            {"league_id": league_id, "roster_id": roster_id},
        )
        if not roster:
            return {"found": False, "roster_key": roster_key}
        profile = fetch_one(
            conn,
            """
            SELECT team_name
            FROM team_profiles
            WHERE league_id = :league_id AND roster_id = :roster_id
            """,
            {"league_id": league_id, "roster_id": roster_id},
        )
        return {
            "found": True,
            "roster_id": roster_id,
            "team_name": profile.get("team_name") if profile else None,
        }

    matches = fetch_all(
        conn,
        """
        SELECT roster_id, team_name
        FROM team_profiles
        WHERE league_id = :league_id
          AND (
            (team_name IS NOT NULL AND lower(team_name) = lower(:key))
            OR (manager_name IS NOT NULL AND lower(manager_name) = lower(:key))
          )
        ORDER BY team_name ASC, manager_name ASC
        """,
        {"league_id": league_id, "key": key},
    )
    if not matches:
        return {"found": False, "roster_key": roster_key}
    if len(matches) > 1:
        return {"found": False, "roster_key": roster_key, "matches": matches}
    return {"found": True, **matches[0]}
