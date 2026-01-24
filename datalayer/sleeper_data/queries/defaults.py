"""Default query helpers for Sleeper data layer."""

from __future__ import annotations

import json
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


def _normalize_lookup_key(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def resolve_player_id(conn, player_key: Any) -> dict[str, Any]:
    key = _normalize_lookup_key(player_key)
    if not key:
        return {"found": False, "player_key": player_key}

    by_id = _fetch_one(
        conn,
        """
        SELECT player_id, full_name
        FROM players
        WHERE player_id = :player_id
        """,
        {"player_id": key},
    )
    if by_id:
        return {"found": True, "player_id": by_id["player_id"], "player_name": by_id["full_name"]}

    matches = _fetch_all(
        conn,
        """
        SELECT player_id, full_name AS player_name
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
    return {"found": True, "player_id": matches[0]["player_id"], "player_name": matches[0]["player_name"]}


def resolve_roster_id(conn, league_id: str, roster_key: Any) -> dict[str, Any]:
    key = _normalize_lookup_key(roster_key)
    if not key:
        return {"found": False, "roster_key": roster_key}

    if key.isdigit():
        roster_id = int(key)
        roster = _fetch_one(
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
        profile = _fetch_one(
            conn,
            """
            SELECT team_name, manager_name
            FROM team_profiles
            WHERE league_id = :league_id AND roster_id = :roster_id
            """,
            {"league_id": league_id, "roster_id": roster_id},
        )
        return {
            "found": True,
            "roster_id": roster_id,
            "team_name": profile.get("team_name") if profile else None,
            "manager_name": profile.get("manager_name") if profile else None,
        }

    matches = _fetch_all(
        conn,
        """
        SELECT roster_id, team_name, manager_name
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


def _parse_player_ids(raw_json: str | None) -> list[str]:
    if not raw_json:
        return []
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [str(pid) for pid in payload if pid]


def _load_player_details(conn, player_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    player_ids = [str(pid) for pid in player_ids]
    if not player_ids:
        return {}
    placeholders = ", ".join([f":p{i}" for i in range(len(player_ids))])
    params = {f"p{i}": pid for i, pid in enumerate(player_ids)}
    rows = _fetch_all(
        conn,
        f"""
        SELECT player_id, full_name, position, nfl_team, status, injury_status
        FROM players
        WHERE player_id IN ({placeholders})
        """,
        params,
    )
    return {row["player_id"]: row for row in rows}


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
            tm.bid_amount,
            p.full_name AS player_name,
            tp.team_name,
            tp.manager_name
        FROM transactions t
        LEFT JOIN transaction_moves tm
            ON tm.transaction_id = t.transaction_id
        LEFT JOIN players p
            ON p.player_id = tm.player_id
        LEFT JOIN team_profiles tp
            ON tp.league_id = t.league_id AND tp.roster_id = tm.roster_id
        WHERE t.week BETWEEN :week_from AND :week_to
        ORDER BY t.week DESC, t.created_ts DESC;
        """,
        {"week_from": week_from, "week_to": week_to},
    )


def get_player_summary(conn, player_key: Any, week_to: int | None = None) -> dict[str, Any]:
    resolved = resolve_player_id(conn, player_key)
    if not resolved.get("found"):
        return {**resolved, "as_of_week": week_to}

    player = _fetch_one(
        conn,
        """
        SELECT player_id, full_name, position, nfl_team, status, injury_status
        FROM players
        WHERE player_id = :player_id
        """,
        {"player_id": resolved["player_id"]},
    )
    if not player:
        return {"player_id": resolved["player_id"], "found": False, "as_of_week": week_to}

    player["player_name"] = player.get("full_name")
    return {"player": player, "found": True, "as_of_week": week_to}


def get_team_dossier(
    conn, league_id: str, roster_key: Any, week: int | None = None
) -> dict[str, Any]:
    resolved = resolve_roster_id(conn, league_id, roster_key)
    if not resolved.get("found"):
        return {**resolved, "as_of_week": week}
    roster_id = resolved["roster_id"]

    team = _fetch_one(
        conn,
        """
        SELECT league_id, roster_id, team_name, manager_name, avatar_url
        FROM team_profiles
        WHERE league_id = :league_id AND roster_id = :roster_id
        """,
        {"league_id": league_id, "roster_id": roster_id},
    )
    if not team:
        return {"roster_id": roster_id, "found": False, "as_of_week": week}

    standings = None
    if week is not None:
        standings = _fetch_one(
            conn,
            """
            SELECT wins, losses, ties, points_for, points_against, rank, streak_type, streak_len
            FROM standings
            WHERE league_id = :league_id AND roster_id = :roster_id AND week = :week
            """,
            {"league_id": league_id, "roster_id": roster_id, "week": week},
        )

    recent_games = _fetch_all(
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
        WHERE g.league_id = :league_id
          AND (g.roster_id_a = :roster_id OR g.roster_id_b = :roster_id)
        ORDER BY week DESC
        LIMIT 5
        """,
        {"league_id": league_id, "roster_id": roster_id},
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


def get_roster_current(conn, roster_id: int) -> dict[str, Any]:
    team = _fetch_one(
        conn,
        """
        SELECT league_id, roster_id, team_name, manager_name, avatar_url
        FROM team_profiles
        WHERE roster_id = :roster_id
        """,
        {"roster_id": roster_id},
    )

    players = _fetch_all(
        conn,
        """
        SELECT
            rp.player_id,
            rp.role,
            p.full_name,
            p.full_name AS player_name,
            p.position,
            p.nfl_team,
            p.status,
            p.injury_status
        FROM roster_players rp
        LEFT JOIN players p
            ON p.player_id = rp.player_id
        WHERE rp.roster_id = :roster_id
        ORDER BY
            CASE rp.role
                WHEN 'starter' THEN 0
                WHEN 'bench' THEN 1
                WHEN 'taxi' THEN 2
                WHEN 'reserve' THEN 3
                WHEN 'ir' THEN 4
                ELSE 5
            END,
            p.full_name ASC
        """,
        {"roster_id": roster_id},
    )

    if not team and not players:
        return {"roster_id": roster_id, "found": False}

    return {
        "team": team,
        "players": players,
        "as_of_week": None,
        "found": True,
    }


def get_roster_snapshot(conn, roster_id: int, week: int) -> dict[str, Any]:
    matchup = _fetch_one(
        conn,
        """
        SELECT players_json, starters_json
        FROM matchups
        WHERE roster_id = :roster_id AND week = :week
        """,
        {"roster_id": roster_id, "week": week},
    )
    if not matchup:
        return {"roster_id": roster_id, "week": week, "found": False}

    player_ids = _parse_player_ids(matchup.get("players_json"))
    starters = set(_parse_player_ids(matchup.get("starters_json")))
    details = _load_player_details(conn, player_ids)

    players = []
    for player_id in player_ids:
        info = details.get(
            player_id,
            {
                "player_id": player_id,
                "full_name": None,
                "player_name": None,
                "position": None,
                "nfl_team": None,
                "status": None,
                "injury_status": None,
            },
        )
        info["player_name"] = info.get("player_name") or info.get("full_name")
        players.append(
            {
                **info,
                "player_id": player_id,
                "role": "starter" if player_id in starters else "bench",
            }
        )

    team = _fetch_one(
        conn,
        """
        SELECT league_id, roster_id, team_name, manager_name, avatar_url
        FROM team_profiles
        WHERE roster_id = :roster_id
        """,
        {"roster_id": roster_id},
    )

    return {
        "team": team,
        "players": players,
        "as_of_week": week,
        "found": True,
    }
