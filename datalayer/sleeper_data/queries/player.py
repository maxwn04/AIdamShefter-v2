"""Player-specific query functions."""

from __future__ import annotations

from typing import Any

from ._helpers import fetch_all, fetch_one, strip_id_fields, strip_id_fields_list
from ._resolvers import resolve_player_id


def get_player_summary(conn, player_key: Any) -> dict[str, Any]:
    """Get basic metadata about an NFL player.

    Returns player identity, position, team, and injury status. Useful for
    looking up player details before querying their performance log.

    Args:
        conn: SQLite database connection.
        player_key: Player name or player_id.

    Returns:
        {
            "found": True,
            "player": {
                "player_name": str,
                "position": str,
                "nfl_team": str,
                "status": str,  # "Active", "Inactive", etc.
                "injury_status": str | None  # "Questionable", "Out", etc.
            }
        }

        Returns {"found": False, "player_key": ...} if player not found.
        If multiple players match the name, returns {"found": False, "matches": [...]}.
    """
    resolved = resolve_player_id(conn, player_key)
    if not resolved.get("found"):
        return {**resolved}

    player = fetch_one(
        conn,
        """
        SELECT player_id, full_name, position, nfl_team, status, injury_status
        FROM players
        WHERE player_id = :player_id
        """,
        {"player_id": resolved["player_id"]},
    )
    if not player:
        return {"found": False, "player_key": player_key}

    player["player_name"] = player.get("full_name")
    del player["full_name"]
    return {"found": True, "player": strip_id_fields(player)}


def _fetch_player_performances(
    conn,
    league_id: str,
    player_id: str,
    week_from: int | None = None,
    week_to: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch player performance rows from the database."""
    params: dict[str, Any] = {"league_id": league_id, "player_id": player_id}
    filters = ["pp.league_id = :league_id", "pp.player_id = :player_id"]
    if week_from is not None:
        params["week_from"] = week_from
        filters.append("pp.week >= :week_from")
    if week_to is not None:
        params["week_to"] = week_to
        filters.append("pp.week <= :week_to")

    return fetch_all(
        conn,
        f"""
        SELECT
            pp.week,
            pp.points,
            pp.role,
            pp.roster_id,
            tp.team_name
        FROM player_performances pp
        LEFT JOIN team_profiles tp
            ON tp.league_id = pp.league_id AND tp.roster_id = pp.roster_id
        WHERE {" AND ".join(filters)}
        ORDER BY pp.week ASC
        """,
        params,
    )


def _build_player_log_response(
    player_name: str, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build the standard player log response structure."""
    performances = strip_id_fields_list(rows)
    weeks_played = len(performances)
    total_points = sum(p.get("points") or 0 for p in performances)
    avg_points = round(total_points / weeks_played, 2) if weeks_played > 0 else 0.0

    return {
        "found": True,
        "player_name": player_name,
        "weeks_played": weeks_played,
        "total_points": round(total_points, 2),
        "avg_points": avg_points,
        "performances": performances,
    }


def get_player_weekly_log(
    conn,
    league_id: str,
    player_key: Any,
    week_from: int | None = None,
    week_to: int | None = None,
) -> dict[str, Any]:
    """Get a player's fantasy performance log, optionally filtered to a week range.

    Returns each week's points, the fantasy team they were on, and whether
    they were started or benched. Includes summary stats for the period.

    Args:
        conn: SQLite database connection.
        league_id: The league identifier.
        player_key: Player name or player_id.
        week_from: Starting week (inclusive). Omit for full season.
        week_to: Ending week (inclusive). Omit for full season.

    Returns:
        {
            "found": True,
            "player_name": str,
            "weeks_played": int,
            "total_points": float,
            "avg_points": float,
            "performances": [
                {
                    "week": int,
                    "points": float,
                    "role": str,  # "starter" or "bench"
                    "team_name": str  # Fantasy team that rostered them
                },
                ...
            ]
        }

        When week_from or week_to is provided, the response also includes
        "week_from" and/or "week_to" keys reflecting the requested range.

        Returns {"found": False, "player_key": ...} if player not found.
    """
    resolved = resolve_player_id(conn, player_key)
    if not resolved.get("found"):
        return {**resolved}

    rows = _fetch_player_performances(
        conn, league_id, resolved["player_id"], week_from=week_from, week_to=week_to
    )
    result = _build_player_log_response(resolved.get("player_name", ""), rows)
    if week_from is not None:
        result["week_from"] = week_from
    if week_to is not None:
        result["week_to"] = week_to
    return result
