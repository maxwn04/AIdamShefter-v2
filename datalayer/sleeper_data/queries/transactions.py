"""Transaction query functions."""

from __future__ import annotations

from typing import Any

from ._helpers import fetch_all, strip_id_fields_list
from ._resolvers import resolve_roster_id


def _fetch_transaction_rows(
    conn, week_from: int, week_to: int, roster_id: int | None = None
) -> list[dict[str, Any]]:
    """Fetch raw transaction rows from the database."""
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


def _group_transaction_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group raw transaction rows into structured transactions."""
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

    return strip_id_fields_list(ordered)


def get_transactions(
    conn, league_id: str, week_from: int, week_to: int
) -> list[dict[str, Any]]:
    """Get all transactions (trades, waivers, free agent pickups) in a week range.

    Returns grouped transactions showing what each team sent and received.
    Useful for tracking roster moves and analyzing trade activity.

    Args:
        conn: SQLite database connection.
        league_id: The league identifier (unused, kept for API consistency).
        week_from: Starting week (inclusive).
        week_to: Ending week (inclusive).

    Returns:
        [
            {
                "week": int,
                "type": str,  # "trade", "waiver", "free_agent"
                "status": str,  # "complete", "failed", etc.
                "created_ts": int,  # Unix timestamp
                "bid_amount": int | None,  # For waiver claims
                "details": [
                    {
                        "team_name": str,
                        "assets_received": [
                            {
                                "asset_type": str,  # "player" or "pick"
                                "player_name": str | None,
                                "position": str | None,
                                "pick_season": str | None,
                                "pick_round": int | None,
                                "pick_original_team_name": str | None
                            },
                            ...
                        ],
                        "assets_sent": [...]  # Same structure
                    },
                    ...  # One entry per team involved
                ]
            },
            ...
        ]
    """
    rows = _fetch_transaction_rows(conn, week_from, week_to)
    return _group_transaction_rows(rows)


def get_team_transactions(
    conn, league_id: str, week_from: int, week_to: int, roster_key: Any
) -> dict[str, Any]:
    """Get a specific team's transactions in a week range.

    Returns grouped transactions showing what the team sent and received.

    Args:
        conn: SQLite database connection.
        league_id: The league identifier.
        week_from: Starting week (inclusive).
        week_to: Ending week (inclusive).
        roster_key: Team name, manager name, or roster_id.

    Returns:
        {
            "found": True,
            "team_name": str,
            "week_from": int,
            "week_to": int,
            "transactions": [...]  # Same structure as get_transactions
        }

        Returns {"found": False, "roster_key": ...} if team not found.
    """
    resolved = resolve_roster_id(conn, league_id, roster_key)
    if not resolved.get("found"):
        return {"found": False, "roster_key": roster_key}

    rows = _fetch_transaction_rows(conn, week_from, week_to, roster_id=resolved["roster_id"])
    transactions = _group_transaction_rows(rows)

    return {
        "found": True,
        "team_name": resolved.get("team_name"),
        "week_from": week_from,
        "week_to": week_to,
        "transactions": transactions,
    }
