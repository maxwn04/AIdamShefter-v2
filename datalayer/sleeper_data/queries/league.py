"""League-wide query functions."""

from __future__ import annotations

from typing import Any

from ._helpers import (
    POSITIONS,
    fetch_all,
    fetch_one,
    organize_players_by_role_and_position,
    strip_id_fields,
    strip_id_fields_list,
)
from ._resolvers import resolve_roster_id


def _build_matchup_player_lookup(
    conn, league_id: str, week: int, matchup_ids: list[int]
) -> dict[tuple[int, int], dict[str, dict[str, list[dict[str, Any]]]]]:
    """Build a lookup of player performances by (matchup_id, roster_id)."""
    if not matchup_ids:
        return {}
    placeholders = ", ".join([f":m{i}" for i in range(len(matchup_ids))])
    params: dict[str, Any] = {"league_id": league_id, "week": week}
    params.update({f"m{i}": mid for i, mid in enumerate(matchup_ids)})
    rows = fetch_all(
        conn,
        f"""
        SELECT
            pp.matchup_id,
            pp.roster_id,
            pp.player_id,
            pp.points,
            pp.role,
            p.full_name,
            p.position,
            p.nfl_team
        FROM player_performances pp
        LEFT JOIN players p
            ON p.player_id = pp.player_id
        WHERE pp.league_id = :league_id
          AND pp.week = :week
          AND pp.matchup_id IN ({placeholders});
        """,
        params,
    )
    # Group rows by (matchup_id, roster_id)
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in rows:
        key = (int(row["matchup_id"]), int(row["roster_id"]))
        grouped.setdefault(key, []).append(
            {
                "player_name": row.get("full_name"),
                "position": row.get("position"),
                "nfl_team": row.get("nfl_team"),
                "points": row.get("points"),
                "role": row.get("role"),
            }
        )
    # Organize each group by role and position
    return {
        key: organize_players_by_role_and_position(players)
        for key, players in grouped.items()
    }


def _build_team_players(
    matchup_lookup: dict[tuple[int, int], dict[str, dict[str, list[dict[str, Any]]]]],
    matchup_id: Any,
    roster_id: Any,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Get player breakdown for a team in a matchup from the lookup."""
    empty_result: dict[str, dict[str, list[dict[str, Any]]]] = {
        "starters": {pos: [] for pos in POSITIONS},
        "bench": {pos: [] for pos in POSITIONS},
    }
    if matchup_id is None or roster_id is None:
        return empty_result
    return matchup_lookup.get((int(matchup_id), int(roster_id)), empty_result)


def get_league_snapshot(conn, week: int | None = None) -> dict[str, Any]:
    """Get a comprehensive snapshot of the league for a specific week.

    Provides standings, all matchup results, and transactions for the week.
    This is the primary entry point for getting a high-level view of league state.

    Args:
        conn: SQLite database connection.
        week: Week number to query. Defaults to the current effective week.

    Returns:
        {
            "found": True,
            "as_of_week": int,
            "league": {
                "name": str,
                "season": str,
                "sport": str,
                "playoff_week_start": int | None
            },
            "standings": [
                {
                    "team_name": str,
                    "wins": int,
                    "losses": int,
                    "ties": int,
                    "points_for": float,
                    "points_against": float,
                    "rank": int
                },
                ...
            ],
            "games": [...],  # See get_week_games for structure
            "transactions": [...]  # See transactions.get_transactions for structure
        }
    """
    # Import here to avoid circular dependency
    from .transactions import get_transactions

    league = fetch_one(
        conn,
        "SELECT league_id, season, name, sport, playoff_week_start FROM leagues LIMIT 1",
    )
    if not league:
        return {"found": False}

    effective_week = week
    if effective_week is None:
        context = fetch_one(
            conn,
            "SELECT effective_week FROM season_context LIMIT 1",
        )
        effective_week = context.get("effective_week") if context else None

    standings = []
    if effective_week is not None:
        standings = fetch_all(
            conn,
            """
            SELECT s.roster_id, s.wins, s.losses, s.ties, s.points_for, s.points_against, s.rank,
                   tp.team_name
            FROM standings s
            LEFT JOIN team_profiles tp
                ON tp.league_id = s.league_id AND tp.roster_id = s.roster_id
            WHERE s.week = :week
            ORDER BY s.rank ASC;
            """,
            {"week": effective_week},
        )

    games = (
        get_week_games(conn, league["league_id"], effective_week)
        if effective_week is not None
        else []
    )
    transactions = (
        get_transactions(conn, league["league_id"], effective_week, effective_week)
        if effective_week is not None
        else []
    )

    return {
        "found": True,
        "as_of_week": effective_week,
        "league": strip_id_fields(league),
        "standings": strip_id_fields_list(standings),
        "games": strip_id_fields_list(games),
        "transactions": strip_id_fields_list(transactions),
    }


def _fetch_games_rows(
    conn,
    league_id: str,
    week: int,
    roster_id: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch raw game rows from the database."""
    params: dict[str, Any] = {"week": week, "league_id": league_id}
    roster_filter = ""
    if roster_id is not None:
        params["roster_id"] = roster_id
        roster_filter = "AND (g.roster_id_a = :roster_id OR g.roster_id_b = :roster_id)"

    return fetch_all(
        conn,
        f"""
        SELECT
            g.week,
            g.matchup_id,
            g.roster_id_a,
            g.roster_id_b,
            g.points_a,
            g.points_b,
            tpa.team_name AS team_a,
            tpb.team_name AS team_b,
            CASE
                WHEN g.winner_roster_id = g.roster_id_a THEN tpa.team_name
                WHEN g.winner_roster_id = g.roster_id_b THEN tpb.team_name
                ELSE NULL
            END AS winner
        FROM games g
        LEFT JOIN team_profiles tpa
            ON tpa.league_id = g.league_id AND tpa.roster_id = g.roster_id_a
        LEFT JOIN team_profiles tpb
            ON tpb.league_id = g.league_id AND tpb.roster_id = g.roster_id_b
        WHERE g.league_id = :league_id AND g.week = :week
        {roster_filter}
        ORDER BY g.matchup_id;
        """,
        params,
    )


def _attach_players_to_games(
    conn, league_id: str, week: int, rows: list[dict[str, Any]]
) -> None:
    """Attach player breakdowns to game rows in-place."""
    matchup_ids = [
        row["matchup_id"] for row in rows if row.get("matchup_id") is not None
    ]
    matchup_lookup = _build_matchup_player_lookup(conn, league_id, week, matchup_ids)
    for row in rows:
        row["team_a_players"] = _build_team_players(
            matchup_lookup,
            row.get("matchup_id"),
            row.get("roster_id_a"),
        )
        row["team_b_players"] = _build_team_players(
            matchup_lookup,
            row.get("matchup_id"),
            row.get("roster_id_b"),
        )


def get_week_games(conn, league_id: str, week: int) -> list[dict[str, Any]]:
    """Get all matchup games for a specific week.

    Returns head-to-head matchups with scores and winner.

    Args:
        conn: SQLite database connection.
        league_id: The league identifier.
        week: The week number to query.

    Returns:
        [
            {
                "week": int,
                "team_a": str,
                "team_b": str,
                "points_a": float,
                "points_b": float,
                "winner": str | None
            },
            ...
        ]
    """
    rows = _fetch_games_rows(conn, league_id, week)
    return strip_id_fields_list(rows)


def get_week_games_with_players(conn, league_id: str, week: int) -> list[dict[str, Any]]:
    """Get all matchup games for a specific week with player breakdowns.

    Returns head-to-head matchups with scores, winner, and full player-by-player
    breakdowns for detailed game analysis.

    Args:
        conn: SQLite database connection.
        league_id: The league identifier.
        week: The week number to query.

    Returns:
        [
            {
                "week": int,
                "team_a": str,
                "team_b": str,
                "points_a": float,
                "points_b": float,
                "winner": str | None,
                "team_a_players": {
                    "starters": {"qb": [...], "rb": [...], ...},
                    "bench": {"qb": [...], ...}
                },
                "team_b_players": {...}
            },
            ...
        ]
    """
    rows = _fetch_games_rows(conn, league_id, week)
    if rows:
        _attach_players_to_games(conn, league_id, week, rows)
    return strip_id_fields_list(rows)


def get_team_game(conn, league_id: str, week: int, roster_key: Any) -> dict[str, Any]:
    """Get a specific team's game for a week.

    Args:
        conn: SQLite database connection.
        league_id: The league identifier.
        week: The week number to query.
        roster_key: Team name, manager name, or roster_id.

    Returns:
        {
            "found": True,
            "as_of_week": int,
            "game": {
                "week": int,
                "team_a": str,
                "team_b": str,
                "points_a": float,
                "points_b": float,
                "winner": str | None
            }
        }

        Returns {"found": False, "roster_key": ...} if team not found.
    """
    resolved = resolve_roster_id(conn, league_id, roster_key)
    if not resolved.get("found"):
        return {"found": False, "roster_key": roster_key, "as_of_week": week}

    rows = _fetch_games_rows(conn, league_id, week, roster_id=resolved["roster_id"])
    if not rows:
        return {"found": False, "roster_key": roster_key, "as_of_week": week}

    games = strip_id_fields_list(rows)
    return {"found": True, "as_of_week": week, "game": games[0]}


def get_team_game_with_players(
    conn, league_id: str, week: int, roster_key: Any
) -> dict[str, Any]:
    """Get a specific team's game for a week with player breakdowns.

    Args:
        conn: SQLite database connection.
        league_id: The league identifier.
        week: The week number to query.
        roster_key: Team name, manager name, or roster_id.

    Returns:
        {
            "found": True,
            "as_of_week": int,
            "game": {
                "week": int,
                "team_a": str,
                "team_b": str,
                "points_a": float,
                "points_b": float,
                "winner": str | None,
                "team_a_players": {
                    "starters": {"qb": [...], "rb": [...], ...},
                    "bench": {"qb": [...], ...}
                },
                "team_b_players": {...}
            }
        }

        Returns {"found": False, "roster_key": ...} if team not found.
    """
    resolved = resolve_roster_id(conn, league_id, roster_key)
    if not resolved.get("found"):
        return {"found": False, "roster_key": roster_key, "as_of_week": week}

    rows = _fetch_games_rows(conn, league_id, week, roster_id=resolved["roster_id"])
    if not rows:
        return {"found": False, "roster_key": roster_key, "as_of_week": week}

    _attach_players_to_games(conn, league_id, week, rows)
    games = strip_id_fields_list(rows)
    return {"found": True, "as_of_week": week, "game": games[0]}


def get_week_player_leaderboard(
    conn, league_id: str, week: int, *, limit: int = 10
) -> list[dict[str, Any]]:
    """Get the top-scoring players for a specific week.

    Returns players ranked by fantasy points scored, useful for identifying
    standout performances and weekly MVPs.

    Args:
        conn: SQLite database connection.
        league_id: The league identifier.
        week: The week number to query.
        limit: Maximum number of players to return. Defaults to 10.

    Returns:
        [
            {
                "rank": int,  # 1-indexed position in leaderboard
                "player_name": str,
                "position": str,
                "nfl_team": str,
                "team_name": str,  # Fantasy team that rostered this player
                "points": float,
                "role": str  # "starter" or "bench"
            },
            ...
        ]
    """
    rows = fetch_all(
        conn,
        """
        SELECT
            pp.player_id,
            pp.points,
            pp.role,
            pp.roster_id,
            p.full_name AS player_name,
            p.position,
            p.nfl_team,
            tp.team_name
        FROM player_performances pp
        LEFT JOIN players p
            ON p.player_id = pp.player_id
        LEFT JOIN team_profiles tp
            ON tp.league_id = pp.league_id AND tp.roster_id = pp.roster_id
        WHERE pp.league_id = :league_id AND pp.week = :week
        ORDER BY pp.points DESC, p.full_name ASC
        LIMIT :limit
        """,
        {"league_id": league_id, "week": week, "limit": limit},
    )
    result = strip_id_fields_list(rows)
    # Add rank field
    for i, row in enumerate(result, start=1):
        row["rank"] = i
    return result
