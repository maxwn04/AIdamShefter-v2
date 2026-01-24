"""Default query helpers for Sleeper data layer."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping


def _fetch_all(conn, sql: str, params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    cur = conn.execute(sql, params or {})
    columns = [col[0] for col in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def _fetch_one(conn, sql: str, params: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    cur = conn.execute(sql, params or {})
    row = cur.fetchone()
    if not row:
        return None
    columns = [col[0] for col in cur.description]
    return dict(zip(columns, row))


def get_week_games(conn, week: int) -> list[dict[str, Any]]:
    rows = _fetch_all(
        conn,
        """
        SELECT
            g.week,
            g.matchup_id,
            g.roster_id_a,
            g.roster_id_b,
            g.points_a,
            g.points_b,
            g.winner_roster_id,
            tpa.team_name AS team_a,
            tpb.team_name AS team_b,
            tpa.manager_name AS manager_a,
            tpb.manager_name AS manager_b
        FROM games g
        LEFT JOIN team_profiles tpa
            ON tpa.league_id = g.league_id AND tpa.roster_id = g.roster_id_a
        LEFT JOIN team_profiles tpb
            ON tpb.league_id = g.league_id AND tpb.roster_id = g.roster_id_b
        WHERE g.week = :week
        ORDER BY g.matchup_id;
        """,
        {"week": week},
    )
    return rows


def get_transactions(conn, week_from: int, week_to: int) -> list[dict[str, Any]]:
    return _fetch_all(
        conn,
        """
        SELECT
            t.week,
            t.transaction_id,
            t.type,
            t.status,
            t.created_ts,
            tm.direction,
            tm.player_id,
            tm.roster_id,
            tm.bid_amount
        FROM transactions t
        LEFT JOIN transaction_moves tm
            ON tm.transaction_id = t.transaction_id
        WHERE t.week BETWEEN :week_from AND :week_to
        ORDER BY t.week DESC, t.created_ts DESC;
        """,
        {"week_from": week_from, "week_to": week_to},
    )


def get_player_summary(conn, player_id: str, week_to: int | None = None) -> dict[str, Any]:
    player = _fetch_one(
        conn,
        """
        SELECT player_id, full_name, position, nfl_team, status, injury_status
        FROM players
        WHERE player_id = :player_id
        """,
        {"player_id": player_id},
    )
    if not player:
        return {"player_id": player_id, "found": False}

    return {"player": player, "found": True, "as_of_week": week_to}


def get_team_dossier(conn, roster_id: int, week: int | None = None) -> dict[str, Any]:
    team = _fetch_one(
        conn,
        """
        SELECT league_id, roster_id, team_name, manager_name, avatar_url
        FROM team_profiles
        WHERE roster_id = :roster_id
        """,
        {"roster_id": roster_id},
    )
    if not team:
        return {"roster_id": roster_id, "found": False}

    standings = None
    if week is not None:
        standings = _fetch_one(
            conn,
            """
            SELECT wins, losses, ties, points_for, points_against, rank, streak_type, streak_len
            FROM standings
            WHERE roster_id = :roster_id AND week = :week
            """,
            {"roster_id": roster_id, "week": week},
        )

    recent_games = _fetch_all(
        conn,
        """
        SELECT week, matchup_id, roster_id_a, roster_id_b, points_a, points_b, winner_roster_id
        FROM games
        WHERE roster_id_a = :roster_id OR roster_id_b = :roster_id
        ORDER BY week DESC
        LIMIT 5
        """,
        {"roster_id": roster_id},
    )

    return {
        "team": team,
        "standings": standings,
        "recent_games": recent_games,
        "as_of_week": week,
        "found": True,
    }


def get_league_snapshot(conn, week: int | None = None) -> dict[str, Any]:
    league = _fetch_one(
        conn,
        "SELECT league_id, season, name, sport FROM leagues LIMIT 1",
    )
    if not league:
        return {"found": False}

    effective_week = week
    if effective_week is None:
        context = _fetch_one(
            conn,
            "SELECT effective_week FROM season_context LIMIT 1",
        )
        effective_week = context.get("effective_week") if context else None

    standings = []
    if effective_week is not None:
        standings = _fetch_all(
            conn,
            """
            SELECT s.roster_id, s.wins, s.losses, s.ties, s.points_for, s.points_against, s.rank,
                   tp.team_name, tp.manager_name
            FROM standings s
            LEFT JOIN team_profiles tp
                ON tp.league_id = s.league_id AND tp.roster_id = s.roster_id
            WHERE s.week = :week
            ORDER BY s.rank ASC;
            """,
            {"week": effective_week},
        )

    games = get_week_games(conn, effective_week) if effective_week is not None else []
    transactions = (
        get_transactions(conn, effective_week, effective_week)
        if effective_week is not None
        else []
    )

    return {
        "league": league,
        "as_of_week": effective_week,
        "standings": standings,
        "games": games,
        "transactions": transactions,
        "found": True,
    }
