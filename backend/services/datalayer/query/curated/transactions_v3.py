"""Collision-safe transaction queries for version-3 snapshots."""

from __future__ import annotations

from typing import Any

from backend.services.datalayer.query.curated._helpers import fetch_all
from backend.services.datalayer.query.curated._resolvers import resolve_roster_id
from backend.services.datalayer.query.curated.transactions import (
    _group_transaction_rows,
)


def _fetch_transaction_rows(
    conn,
    league_id: str,
    season: str,
    week_from: int,
    week_to: int,
    roster_id: int | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "league_id": league_id,
        "season": season,
        "week_from": week_from,
        "week_to": week_to,
    }
    roster_filter = ""
    if roster_id is not None:
        params["roster_id"] = roster_id
        roster_filter = """
        AND EXISTS (
            SELECT 1
            FROM transaction_moves AS selected_move
            WHERE selected_move.league_id = t.league_id
              AND selected_move.transaction_id = t.transaction_id
              AND selected_move.roster_id = :roster_id
        )
        """

    return fetch_all(
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
        FROM transactions AS t
        LEFT JOIN transaction_moves AS tm
          ON tm.league_id = t.league_id
         AND tm.transaction_id = t.transaction_id
        LEFT JOIN players AS p
          ON p.player_id = tm.player_id
        LEFT JOIN team_profiles AS tp
          ON tp.league_id = t.league_id
         AND tp.roster_id = tm.roster_id
        LEFT JOIN team_profiles AS tp_orig
          ON tp_orig.league_id = t.league_id
         AND tp_orig.roster_id = tm.pick_original_roster_id
        WHERE t.league_id = :league_id
          AND t.season = :season
          AND t.week BETWEEN :week_from AND :week_to
        {roster_filter}
        ORDER BY t.week DESC, t.created_ts DESC;
        """,
        params,
    )


def get_transactions(
    conn, league_id: str, season: str, week_from: int, week_to: int
) -> list[dict[str, Any]]:
    rows = _fetch_transaction_rows(conn, league_id, season, week_from, week_to)
    return _group_transaction_rows(rows)


def get_team_transactions(
    conn,
    league_id: str,
    season: str,
    week_from: int,
    week_to: int,
    roster_key: Any,
) -> dict[str, Any]:
    resolved = resolve_roster_id(conn, league_id, roster_key)
    if not resolved.get("found"):
        return {"found": False, "roster_key": roster_key}

    rows = _fetch_transaction_rows(
        conn,
        league_id,
        season,
        week_from,
        week_to,
        roster_id=resolved["roster_id"],
    )
    return {
        "found": True,
        "team_name": resolved.get("team_name"),
        "week_from": week_from,
        "week_to": week_to,
        "transactions": _group_transaction_rows(rows),
    }


__all__ = ["get_team_transactions", "get_transactions"]
