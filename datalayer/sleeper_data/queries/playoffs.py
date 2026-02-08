"""Playoff bracket query functions."""

from __future__ import annotations

from typing import Any

from ._helpers import fetch_all, fetch_one
from ._resolvers import resolve_roster_id


def get_playoff_bracket(
    conn, league_id: str, bracket_type: str | None = None
) -> dict[str, Any]:
    """Get the playoff bracket structure with team names and results.

    Fetches all playoff matchups, resolves team names via LEFT JOINs, and
    organizes by bracket_type and round. Each matchup includes status
    (complete/pending), team names (or progression labels like "Winner of
    Match 1"), and placements.

    Args:
        conn: SQLite database connection.
        league_id: The league identifier.
        bracket_type: "winners" or "losers". If None, returns both brackets.

    Returns:
        {
            "found": True,
            "brackets": {
                "winners": {
                    "rounds": {
                        1: [{"matchup_id": int, "round": int, ...}, ...],
                        2: [...]
                    },
                    "champion": str | None,
                    "placements": [{"placement": int, "team_name": str}, ...]
                },
                "losers": { ... }
            }
        }

        Returns {"found": False} if no bracket data exists.
    """
    params: dict[str, Any] = {"league_id": league_id}
    type_filter = ""
    if bracket_type is not None:
        type_filter = "AND pm.bracket_type = :bracket_type"
        params["bracket_type"] = bracket_type

    rows = fetch_all(
        conn,
        f"""
        SELECT
            pm.bracket_type,
            pm.round,
            pm.matchup_id,
            pm.t1_roster_id,
            pm.t2_roster_id,
            pm.t1_from_matchup_id,
            pm.t1_from_outcome,
            pm.t2_from_matchup_id,
            pm.t2_from_outcome,
            pm.winner_roster_id,
            pm.loser_roster_id,
            pm.placement,
            tp1.team_name AS t1_team_name,
            tp2.team_name AS t2_team_name,
            tpw.team_name AS winner_team_name,
            tpl.team_name AS loser_team_name
        FROM playoff_matchups pm
        LEFT JOIN team_profiles tp1
            ON tp1.league_id = pm.league_id AND tp1.roster_id = pm.t1_roster_id
        LEFT JOIN team_profiles tp2
            ON tp2.league_id = pm.league_id AND tp2.roster_id = pm.t2_roster_id
        LEFT JOIN team_profiles tpw
            ON tpw.league_id = pm.league_id AND tpw.roster_id = pm.winner_roster_id
        LEFT JOIN team_profiles tpl
            ON tpl.league_id = pm.league_id AND tpl.roster_id = pm.loser_roster_id
        WHERE pm.league_id = :league_id {type_filter}
        ORDER BY pm.bracket_type, pm.round, pm.matchup_id
        """,
        params,
    )

    if not rows:
        return {"found": False}

    brackets: dict[str, dict[str, Any]] = {}

    for row in rows:
        bt = row["bracket_type"]
        if bt not in brackets:
            brackets[bt] = {"rounds": {}, "champion": None, "placements": []}

        rd = row["round"]
        if rd not in brackets[bt]["rounds"]:
            brackets[bt]["rounds"][rd] = []

        def _team_label(roster_id, team_name, from_matchup_id, from_outcome):
            if team_name is not None:
                return team_name
            if roster_id is not None:
                return f"Roster {roster_id}"
            if from_matchup_id is not None:
                label = "Winner" if from_outcome == "w" else "Loser"
                return f"{label} of Match {from_matchup_id}"
            return None

        team_1 = _team_label(
            row["t1_roster_id"],
            row["t1_team_name"],
            row["t1_from_matchup_id"],
            row["t1_from_outcome"],
        )
        team_2 = _team_label(
            row["t2_roster_id"],
            row["t2_team_name"],
            row["t2_from_matchup_id"],
            row["t2_from_outcome"],
        )

        status = "complete" if row["winner_roster_id"] is not None else "pending"

        matchup: dict[str, Any] = {
            "matchup_id": row["matchup_id"],
            "round": rd,
            "team_1": team_1,
            "team_2": team_2,
            "winner": row["winner_team_name"],
            "loser": row["loser_team_name"],
            "status": status,
        }
        if row["placement"] is not None:
            matchup["placement"] = row["placement"]

        brackets[bt]["rounds"][rd].append(matchup)

        if row["placement"] is not None and row["winner_team_name"] is not None:
            brackets[bt]["placements"].append(
                {
                    "placement": row["placement"],
                    "team_name": row["winner_team_name"],
                }
            )
            if row["placement"] == 1:
                brackets[bt]["champion"] = row["winner_team_name"]

    # Sort placements by placement number
    for bt_data in brackets.values():
        bt_data["placements"].sort(key=lambda x: x["placement"])

    return {"found": True, "brackets": brackets}


def get_team_playoff_path(
    conn, league_id: str, roster_key: Any
) -> dict[str, Any]:
    """Get a specific team's playoff bracket journey.

    Resolves the team via roster_key, then fetches all bracket matchups where
    the team appears as a participant (t1, t2) or result (winner, loser).

    Args:
        conn: SQLite database connection.
        league_id: The league identifier.
        roster_key: Team name, manager name, or roster_id.

    Returns:
        {
            "found": True,
            "team_name": str,
            "bracket_type": str,  # "winners" or "losers" (first bracket they appear in)
            "matchups": [
                {
                    "round": int,
                    "matchup_id": int,
                    "opponent": str | None,
                    "result": "win" | "loss" | "pending",
                    "placement": int | None
                },
                ...
            ],
            "final_placement": int | None,
            "is_eliminated": bool,
            "is_champion": bool
        }

        Returns {"found": False, "roster_key": ...} if team not found or not in playoffs.
    """
    resolved = resolve_roster_id(conn, league_id, roster_key)
    if not resolved.get("found"):
        return {**resolved}
    roster_id = resolved["roster_id"]
    team_name = resolved.get("team_name")

    rows = fetch_all(
        conn,
        """
        SELECT
            pm.bracket_type,
            pm.round,
            pm.matchup_id,
            pm.t1_roster_id,
            pm.t2_roster_id,
            pm.winner_roster_id,
            pm.loser_roster_id,
            pm.placement,
            tp1.team_name AS t1_team_name,
            tp2.team_name AS t2_team_name
        FROM playoff_matchups pm
        LEFT JOIN team_profiles tp1
            ON tp1.league_id = pm.league_id AND tp1.roster_id = pm.t1_roster_id
        LEFT JOIN team_profiles tp2
            ON tp2.league_id = pm.league_id AND tp2.roster_id = pm.t2_roster_id
        WHERE pm.league_id = :league_id
          AND (
            pm.t1_roster_id = :roster_id
            OR pm.t2_roster_id = :roster_id
            OR pm.winner_roster_id = :roster_id
            OR pm.loser_roster_id = :roster_id
          )
        ORDER BY pm.bracket_type, pm.round, pm.matchup_id
        """,
        {"league_id": league_id, "roster_id": roster_id},
    )

    if not rows:
        return {"found": False, "roster_key": roster_key}

    matchups: list[dict[str, Any]] = []
    final_placement: int | None = None
    is_eliminated = False
    is_champion = False
    bracket_type: str | None = None

    for row in rows:
        if bracket_type is None:
            bracket_type = row["bracket_type"]

        is_t1 = row["t1_roster_id"] == roster_id
        opponent_name = row["t2_team_name"] if is_t1 else row["t1_team_name"]

        if row["winner_roster_id"] == roster_id:
            result = "win"
        elif row["loser_roster_id"] == roster_id:
            result = "loss"
            is_eliminated = True
        else:
            result = "pending"

        entry: dict[str, Any] = {
            "round": row["round"],
            "matchup_id": row["matchup_id"],
            "opponent": opponent_name,
            "result": result,
        }

        if row["placement"] is not None:
            entry["placement"] = row["placement"]
            if row["winner_roster_id"] == roster_id:
                final_placement = row["placement"]
                if row["placement"] == 1:
                    is_champion = True

        matchups.append(entry)

    return {
        "found": True,
        "team_name": team_name,
        "bracket_type": bracket_type,
        "matchups": matchups,
        "final_placement": final_placement,
        "is_eliminated": is_eliminated,
        "is_champion": is_champion,
    }
