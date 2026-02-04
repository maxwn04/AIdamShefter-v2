"""Team-specific query functions."""

from __future__ import annotations

from typing import Any

from ._helpers import (
    clean_team_profile,
    fetch_all,
    fetch_one,
    format_record,
    organize_players_by_role_and_position,
    strip_id_fields,
    strip_id_fields_list,
)
from ._resolvers import resolve_roster_id


def get_team_dossier(
    conn, league_id: str, roster_key: Any, week: int | None = None
) -> dict[str, Any]:
    """Get a comprehensive profile of a team including standings and recent games.

    Provides team identity, current standings, and the last 5 games for context
    on recent performance and trajectory.

    Args:
        conn: SQLite database connection.
        league_id: The league identifier.
        roster_key: Team name, manager name, or roster_id (int).
        week: Week number for standings. Defaults to current effective week.

    Returns:
        {
            "found": True,
            "as_of_week": int,
            "team": {
                "team_name": str,
                "manager_name": str
            },
            "standings": {
                "wins": int,
                "losses": int,
                "ties": int,
                "record": str,  # e.g., "7-3" or "7-3-1"
                "rank": int,
                "points_for": float,
                "points_against": float,
                "streak_type": str | None,  # "W" or "L"
                "streak_len": int | None
            },
            "recent_games": [
                {
                    "week": int,
                    "team_a": str,
                    "team_b": str,
                    "points_a": float,
                    "points_b": float,
                    "manager_a": str,
                    "manager_b": str
                },
                ...  # Last 5 games, most recent first
            ]
        }

        Returns {"found": False, "roster_key": ...} if team not found.
    """
    resolved = resolve_roster_id(conn, league_id, roster_key)
    if not resolved.get("found"):
        return {**resolved, "as_of_week": week}
    roster_id = resolved["roster_id"]

    team = fetch_one(
        conn,
        """
        SELECT league_id, roster_id, team_name, manager_name
        FROM team_profiles
        WHERE league_id = :league_id AND roster_id = :roster_id
        """,
        {"league_id": league_id, "roster_id": roster_id},
    )
    if not team:
        return {"roster_id": roster_id, "found": False, "as_of_week": week}

    standings = None
    effective_week = week
    if effective_week is None:
        context = fetch_one(conn, "SELECT effective_week FROM season_context LIMIT 1")
        effective_week = context.get("effective_week") if context else None

    if effective_week is not None:
        standings = fetch_one(
            conn,
            """
            SELECT wins, losses, ties, points_for, points_against, rank, streak_type, streak_len
            FROM standings
            WHERE league_id = :league_id AND roster_id = :roster_id AND week = :week
            """,
            {"league_id": league_id, "roster_id": roster_id, "week": effective_week},
        )
        if standings:
            standings["record"] = format_record(
                standings.get("wins"),
                standings.get("losses"),
                standings.get("ties"),
            )

    recent_games = fetch_all(
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
        "found": True,
        "as_of_week": effective_week,
        "team": clean_team_profile(team),
        "standings": strip_id_fields(standings),
        "recent_games": strip_id_fields_list(recent_games),
    }


def get_team_schedule(conn, league_id: str, roster_key: Any) -> dict[str, Any]:
    """Get the full season schedule for a team with game-by-game results.

    Shows all regular season and playoff games with opponent, scores, results,
    and cumulative record after each week. Useful for analyzing a team's
    season trajectory and strength of schedule.

    Args:
        conn: SQLite database connection.
        league_id: The league identifier.
        roster_key: Team name, manager name, or roster_id (int).

    Returns:
        {
            "found": True,
            "as_of_week": int,
            "team_name": str,
            "regular_season_games": [
                {
                    "week": int,
                    "opponent_name": str,
                    "team_points": float,
                    "opponent_points": float,
                    "result": str,  # "W", "L", or "T"
                    "record_after_week": str  # e.g., "5-2"
                },
                ...
            ],
            "playoff_games": [...]  # Same structure, for playoff weeks
        }

        Returns {"found": False, "roster_key": ...} if team not found.
    """
    resolved = resolve_roster_id(conn, league_id, roster_key)
    if not resolved.get("found"):
        return {**resolved, "as_of_week": None}
    roster_id = resolved["roster_id"]

    roster_row = fetch_one(
        conn,
        """
        SELECT record_string
        FROM rosters
        WHERE league_id = :league_id AND roster_id = :roster_id
        """,
        {"league_id": league_id, "roster_id": roster_id},
    )
    record_string = roster_row.get("record_string") if roster_row else None

    league_row = fetch_one(
        conn,
        """
        SELECT league_average_match, playoff_week_start
        FROM leagues
        WHERE league_id = :league_id
        """,
        {"league_id": league_id},
    )
    league_average_match = league_row.get("league_average_match") if league_row else None
    playoff_week_start = league_row.get("playoff_week_start") if league_row else None
    chars_per_week = 2 if league_average_match == 1 else 1

    rows = fetch_all(
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
            tpb.team_name AS team_b
        FROM games g
        LEFT JOIN team_profiles tpa
            ON tpa.league_id = g.league_id AND tpa.roster_id = g.roster_id_a
        LEFT JOIN team_profiles tpb
            ON tpb.league_id = g.league_id AND tpb.roster_id = g.roster_id_b
        WHERE g.league_id = :league_id
          AND (g.roster_id_a = :roster_id OR g.roster_id_b = :roster_id)
        ORDER BY g.week ASC, g.matchup_id ASC
        """,
        {"league_id": league_id, "roster_id": roster_id},
    )

    context = fetch_one(conn, "SELECT effective_week FROM season_context LIMIT 1")
    current_week = context.get("effective_week") if context else None

    def _record_for_week(week: int | None) -> str | None:
        if not record_string or week is None:
            return None
        if current_week is not None and week > int(current_week):
            return None
        record_value = "".join(ch for ch in str(record_string).upper() if ch.strip())
        if not record_value:
            return None
        cutoff = int(week) * chars_per_week
        if len(record_value) < cutoff:
            return None
        wins = 0
        losses = 0
        ties = 0
        for outcome in record_value[:cutoff]:
            if outcome == "W":
                wins += 1
            elif outcome == "L":
                losses += 1
            elif outcome == "T":
                ties += 1
        return format_record(wins, losses, ties)

    schedule_regular: list[dict[str, Any]] = []
    schedule_playoffs: list[dict[str, Any]] = []

    for row in rows:
        week = row.get("week")
        is_team_a = row.get("roster_id_a") == roster_id
        team_points = row.get("points_a") if is_team_a else row.get("points_b")
        opponent_points = row.get("points_b") if is_team_a else row.get("points_a")
        opponent_name = row.get("team_b") if is_team_a else row.get("team_a")

        result = None
        winner_id = row.get("winner_roster_id")
        if winner_id is not None:
            result = "W" if int(winner_id) == int(roster_id) else "L"
        elif team_points is not None and opponent_points is not None:
            if team_points > opponent_points:
                result = "W"
            elif team_points < opponent_points:
                result = "L"
            else:
                result = "T"

        entry: dict[str, Any] = {
            "week": week,
            "opponent_name": opponent_name,
            "team_points": team_points,
            "opponent_points": opponent_points,
            "result": result,
        }
        if chars_per_week == 2 and record_string and week is not None:
            record_value = "".join(ch for ch in str(record_string).upper() if ch.strip())
            cutoff = int(week) * chars_per_week
            if len(record_value) >= cutoff:
                entry["result"] = record_value[cutoff - chars_per_week : cutoff]
        record = _record_for_week(int(week)) if week is not None else None
        if record is not None:
            entry["record_after_week"] = record
        if playoff_week_start is not None and week is not None and int(week) >= int(
            playoff_week_start
        ):
            schedule_playoffs.append(entry)
        else:
            schedule_regular.append(entry)

    return {
        "found": True,
        "as_of_week": current_week,
        "team_name": resolved.get("team_name"),
        "regular_season_games": schedule_regular,
        "playoff_games": schedule_playoffs,
    }


def get_roster_current(conn, league_id: str, roster_key: Any) -> dict[str, Any]:
    """Get a team's current roster composition.

    Returns all players on the roster organized by role (starter/bench) and
    position. Also includes draft picks currently owned by this team.

    Args:
        conn: SQLite database connection.
        league_id: The league identifier.
        roster_key: Team name, manager name, or roster_id (int).

    Returns:
        {
            "found": True,
            "team": {
                "team_name": str,
                "manager_name": str
            },
            "roster": {
                "starters": {
                    "qb": [{"player_name": str, "position": str, "nfl_team": str, ...}],
                    "rb": [...], "wr": [...], "te": [...], "k": [...], "def": [...]
                },
                "bench": {...}  # Same structure
            },
            "picks": [
                {
                    "season": str,
                    "round": int,
                    "original_team_name": str,
                    "current_team_name": str
                },
                ...
            ]
        }

        Returns {"found": False, "roster_key": ...} if team not found.
    """
    resolved = resolve_roster_id(conn, league_id, roster_key)
    if not resolved.get("found"):
        return {**resolved}
    roster_id = resolved["roster_id"]

    team = fetch_one(
        conn,
        """
        SELECT league_id, roster_id, team_name, manager_name
        FROM team_profiles
        WHERE league_id = :league_id AND roster_id = :roster_id
        """,
        {"league_id": league_id, "roster_id": roster_id},
    )

    players = fetch_all(
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
        """,
        {"league_id": league_id, "roster_id": roster_id},
    )

    picks = fetch_all(
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
        return {"found": False, "roster_key": roster_key}

    roster = organize_players_by_role_and_position(strip_id_fields_list(players))

    return {
        "found": True,
        "team": clean_team_profile(team),
        "roster": roster,
        "picks": strip_id_fields_list(picks),
    }


def get_roster_snapshot(conn, league_id: str, roster_key: Any, week: int) -> dict[str, Any]:
    """Get a team's roster as it was during a specific week.

    Returns the players who were on the roster that week with their points
    scored, organized by role and position. Useful for historical analysis
    and reviewing past lineup decisions.

    Args:
        conn: SQLite database connection.
        league_id: The league identifier.
        roster_key: Team name, manager name, or roster_id (int).
        week: The week number to query.

    Returns:
        {
            "found": True,
            "as_of_week": int,
            "team": {
                "team_name": str,
                "manager_name": str
            },
            "roster": {
                "starters": {
                    "qb": [{"player_name": str, "points": float, ...}],
                    "rb": [...], "wr": [...], "te": [...], "k": [...], "def": [...]
                },
                "bench": {...}  # Same structure
            }
        }

        Returns {"found": False, "roster_key": ...} if team or week data not found.
    """
    resolved = resolve_roster_id(conn, league_id, roster_key)
    if not resolved.get("found"):
        return {**resolved}
    roster_id = resolved["roster_id"]

    players = fetch_all(
        conn,
        """
        SELECT
            pp.player_id,
            pp.role,
            pp.points,
            p.full_name AS player_name,
            p.position,
            p.nfl_team
        FROM player_performances pp
        LEFT JOIN players p
            ON p.player_id = pp.player_id
        WHERE pp.league_id = :league_id
          AND pp.roster_id = :roster_id
          AND pp.week = :week
        """,
        {"league_id": league_id, "roster_id": roster_id, "week": week},
    )
    if not players:
        return {"found": False, "roster_key": roster_key, "week": week}

    team = fetch_one(
        conn,
        """
        SELECT league_id, roster_id, team_name, manager_name
        FROM team_profiles
        WHERE league_id = :league_id AND roster_id = :roster_id
        """,
        {"league_id": league_id, "roster_id": roster_id},
    )

    roster = organize_players_by_role_and_position(strip_id_fields_list(players))

    return {
        "found": True,
        "as_of_week": week,
        "team": clean_team_profile(team),
        "roster": roster,
    }
