"""Default query helpers for Sleeper data layer."""

from __future__ import annotations

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

    matches = _fetch_all(
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

    matches = _fetch_all(
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


def _strip_id_fields_recursive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_id_fields_recursive(val)
            for key, val in value.items()
            if not key.endswith("_id")
        }
    if isinstance(value, list):
        return [_strip_id_fields_recursive(item) for item in value]
    return value


def _strip_id_fields(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    return _strip_id_fields_recursive(payload)


def _strip_id_fields_list(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_strip_id_fields_recursive(item) for item in items]


def _build_matchup_player_lookup(
    conn, league_id: str, week: int, matchup_ids: list[int]
) -> dict[tuple[int, int], list[dict[str, Any]]]:
    if not matchup_ids:
        return {}
    placeholders = ", ".join([f":m{i}" for i in range(len(matchup_ids))])
    params = {"league_id": league_id, "week": week}
    params.update({f"m{i}": mid for i, mid in enumerate(matchup_ids)})
    rows = _fetch_all(
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
          AND pp.matchup_id IN ({placeholders})
        ORDER BY pp.matchup_id ASC, pp.roster_id ASC, pp.points DESC;
        """,
        params,
    )
    lookup: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in rows:
        key = (int(row["matchup_id"]), int(row["roster_id"]))
        lookup.setdefault(key, []).append(
            {
                "player_name": row.get("full_name"),
                "position": row.get("position"),
                "nfl_team": row.get("nfl_team"),
                "points": row.get("points"),
                "role": row.get("role"),
            }
        )
    return lookup


def _build_team_players(
    matchup_lookup: dict[tuple[int, int], list[dict[str, Any]]],
    matchup_id: Any,
    roster_id: Any,
) -> list[dict[str, Any]]:
    if matchup_id is None or roster_id is None:
        return []
    return matchup_lookup.get((int(matchup_id), int(roster_id)), [])


def get_week_games(
    conn,
    league_id: str,
    week: int,
    roster_key: Any | None = None,
    *,
    include_players: bool = False,
) -> list[dict[str, Any]] | dict[str, Any]:
    roster_id = None
    if roster_key is not None:
        resolved = resolve_roster_id(conn, league_id, roster_key)
        if not resolved.get("found"):
            return {"found": False, "roster_key": roster_key, "as_of_week": week}
        roster_id = resolved["roster_id"]

    params: dict[str, Any] = {"week": week, "league_id": league_id}
    roster_filter = ""
    if roster_id is not None:
        params["roster_id"] = roster_id
        roster_filter = "AND (g.roster_id_a = :roster_id OR g.roster_id_b = :roster_id)"

    rows = _fetch_all(
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
    if not rows:
        if roster_key is None:
            return []
        return {"found": False, "roster_id": roster_id, "as_of_week": week, "games": []}

    if include_players:
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

    games = _strip_id_fields_list(rows)
    if roster_key is None:
        return games
    return {"found": True, "roster_id": roster_id, "as_of_week": week, "games": games}


def get_week_player_leaderboard(
    conn, league_id: str, week: int, *, limit: int = 10
) -> list[dict[str, Any]]:
    rows = _fetch_all(
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
    return _strip_id_fields_list(rows)


def get_player_weekly_log(
    conn,
    league_id: str,
    player_key: Any,
    *,
    week_from: int | None = None,
    week_to: int | None = None,
) -> dict[str, Any]:
    resolved = resolve_player_id(conn, player_key)
    if not resolved.get("found"):
        return {**resolved, "as_of_week": week_to}

    params: dict[str, Any] = {"league_id": league_id, "player_id": resolved["player_id"]}
    filters = ["pp.league_id = :league_id", "pp.player_id = :player_id"]
    if week_from is not None:
        params["week_from"] = week_from
        filters.append("pp.week >= :week_from")
    if week_to is not None:
        params["week_to"] = week_to
        filters.append("pp.week <= :week_to")

    rows = _fetch_all(
        conn,
        f"""
        SELECT
            pp.week,
            pp.points,
            pp.role,
            pp.roster_id,
            pp.matchup_id,
            tp.team_name
        FROM player_performances pp
        LEFT JOIN team_profiles tp
            ON tp.league_id = pp.league_id AND tp.roster_id = pp.roster_id
        WHERE {" AND ".join(filters)}
        ORDER BY pp.week ASC
        """,
        params,
    )

    return {
        "player_id": resolved["player_id"],
        "player_name": resolved.get("player_name"),
        "performances": _strip_id_fields_list(rows),
        "as_of_week": week_to,
        "found": True,
    }


def get_transactions(
    conn,
    league_id: str,
    week_from: int,
    week_to: int,
    roster_key: Any | None = None,
) -> list[dict[str, Any]]:
    roster_id = None
    if roster_key is not None:
        resolved = resolve_roster_id(conn, league_id, roster_key)
        if not resolved.get("found"):
            return []
        roster_id = resolved["roster_id"]

    params: dict[str, Any] = {"week_from": week_from, "week_to": week_to}
    roster_filter = ""
    if roster_id is not None:
        params["roster_id"] = roster_id
        roster_filter = """
        AND t.transaction_id IN (
            SELECT transaction_id
            FROM transaction_moves
            WHERE roster_id = :roster_id
        )
        """

    rows = _fetch_all(
        conn,
        f"""
        SELECT
            t.week,
            t.transaction_id,
            t.type,
            t.status,
            t.created_ts,
            tm.asset_type,
            tm.direction,
            tm.roster_id,
            tm.player_id,
            p.full_name AS player_name,
            p.position,
            p.age,
            p.years_exp,
            tm.bid_amount,
            tm.pick_season,
            tm.pick_round,
            tm.pick_original_roster_id,
            tm.pick_id,
            tm.from_roster_id,
            tm.to_roster_id,
            tp.team_name,
            tp_orig.team_name AS pick_original_team_name
        FROM transactions t
        LEFT JOIN transaction_moves tm
            ON tm.transaction_id = t.transaction_id
        LEFT JOIN players p
            ON p.player_id = tm.player_id
        LEFT JOIN team_profiles tp
            ON tp.league_id = t.league_id AND tp.roster_id = tm.roster_id
        LEFT JOIN team_profiles tp_orig
            ON tp_orig.league_id = t.league_id AND tp_orig.roster_id = tm.pick_original_roster_id
        WHERE t.week BETWEEN :week_from AND :week_to
        {roster_filter}
        ORDER BY t.week DESC, t.created_ts DESC;
        """,
        params,
    )

    grouped: dict[str, dict[str, Any]] = {}
    ordered: list[dict[str, Any]] = []
    details_by_team: dict[str, dict[str, dict[str, Any]]] = {}

    for row in rows:
        transaction_id = row["transaction_id"]
        if transaction_id not in grouped:
            grouped[transaction_id] = {
                "week": row["week"],
                "type": row["type"],
                "status": row["status"],
                "created_ts": row["created_ts"],
            }
            details_by_team[transaction_id] = {}
            ordered.append(grouped[transaction_id])

        asset_type = row.get("asset_type")
        direction = row.get("direction")
        if asset_type is None and direction is None:
            continue

        asset = {
            "asset_type": asset_type,
            "player_name": row.get("player_name"),
            "position": row.get("position"),
            "age": row.get("age"),
            "years_exp": row.get("years_exp"),
            "pick_season": row.get("pick_season"),
            "pick_round": row.get("pick_round"),
            "pick_original_team_name": row.get("pick_original_team_name"),
        }
        asset = {key: value for key, value in asset.items() if value is not None}

        if direction in {"add", "pick_in"}:
            bucket = "assets_received"
        elif direction in {"drop", "pick_out"}:
            bucket = "assets_sent"
        else:
            bucket = "assets_received"

        if row.get("bid_amount") is not None and row.get("type") != "trade":
            grouped[transaction_id]["bid_amount"] = row.get("bid_amount")

        team_name = row.get("team_name") or "Unknown"
        details = details_by_team[transaction_id].setdefault(
            team_name,
            {"team_name": team_name, "assets_sent": [], "assets_received": []},
        )
        details[bucket].append(asset)

    for transaction_id, grouped_row in grouped.items():
        grouped_row["details"] = list(details_by_team[transaction_id].values())

    return _strip_id_fields_list(ordered)


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
    return {"player": _strip_id_fields(player), "found": True, "as_of_week": week_to}


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
        "team": _strip_id_fields(team),
        "standings": _strip_id_fields(standings),
        "recent_games": _strip_id_fields_list(recent_games),
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
        "league": _strip_id_fields(league),
        "as_of_week": effective_week,
        "standings": _strip_id_fields_list(standings),
        "games": _strip_id_fields_list(games),
        "transactions": _strip_id_fields_list(transactions),
        "found": True,
    }


def get_roster_current(conn, league_id: str, roster_key: Any) -> dict[str, Any]:
    resolved = resolve_roster_id(conn, league_id, roster_key)
    if not resolved.get("found"):
        return {**resolved, "as_of_week": None}
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
        WHERE rp.league_id = :league_id AND rp.roster_id = :roster_id
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
        {"league_id": league_id, "roster_id": roster_id},
    )

    picks = _fetch_all(
        conn,
        """
        SELECT
            dp.season,
            dp.round,
            dp.original_roster_id,
            dp.current_roster_id,
            tpo.team_name AS original_team_name,
            tpc.team_name AS current_team_name
        FROM draft_picks dp
        LEFT JOIN team_profiles tpo
            ON tpo.league_id = dp.league_id AND tpo.roster_id = dp.original_roster_id
        LEFT JOIN team_profiles tpc
            ON tpc.league_id = dp.league_id AND tpc.roster_id = dp.current_roster_id
        WHERE dp.league_id = :league_id AND dp.current_roster_id = :roster_id
        ORDER BY dp.season ASC, dp.round ASC
        """,
        {"league_id": league_id, "roster_id": roster_id},
    )

    if not team and not players and not picks:
        return {"roster_id": roster_id, "found": False, "as_of_week": None}

    return {
        "team": _strip_id_fields(team),
        "players": _strip_id_fields_list(players),
        "picks": _strip_id_fields_list(picks),
        "as_of_week": None,
        "found": True,
    }


def get_roster_snapshot(conn, league_id: str, roster_key: Any, week: int) -> dict[str, Any]:
    resolved = resolve_roster_id(conn, league_id, roster_key)
    if not resolved.get("found"):
        return {**resolved, "as_of_week": week}
    roster_id = resolved["roster_id"]

    players = _fetch_all(
        conn,
        """
        SELECT
            pp.player_id,
            pp.role,
            pp.points,
            p.full_name,
            p.full_name AS player_name,
            p.position,
            p.nfl_team,
            p.status,
            p.injury_status
        FROM player_performances pp
        LEFT JOIN players p
            ON p.player_id = pp.player_id
        WHERE pp.league_id = :league_id
          AND pp.roster_id = :roster_id
          AND pp.week = :week
        ORDER BY
            CASE pp.role
                WHEN 'starter' THEN 0
                WHEN 'bench' THEN 1
                WHEN 'taxi' THEN 2
                WHEN 'reserve' THEN 3
                WHEN 'ir' THEN 4
                ELSE 5
            END,
            p.full_name ASC
        """,
        {"league_id": league_id, "roster_id": roster_id, "week": week},
    )
    if not players:
        return {"roster_id": roster_id, "week": week, "found": False, "as_of_week": week}

    team = _fetch_one(
        conn,
        """
        SELECT league_id, roster_id, team_name, manager_name, avatar_url
        FROM team_profiles
        WHERE league_id = :league_id AND roster_id = :roster_id
        """,
        {"league_id": league_id, "roster_id": roster_id},
    )

    return {
        "team": _strip_id_fields(team),
        "players": _strip_id_fields_list(players),
        "as_of_week": week,
        "found": True,
    }
