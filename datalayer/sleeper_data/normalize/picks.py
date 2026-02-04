"""Normalization functions for draft picks."""

from __future__ import annotations

import sqlite3
from typing import Any

from ..schema.models import DraftPick, Roster


def seed_draft_picks(
    rosters: list[Roster],
    league_id: str,
    base_season: str,
    draft_rounds: int,
) -> list[DraftPick]:
    """Create initial draft picks for future seasons.

    Seeds picks for the next 3 seasons based on current rosters. Each roster
    gets one pick per round, with original and current owner set to the same
    roster (ownership updates come from traded_picks).

    Args:
        rosters: List of Roster objects in the league.
        league_id: The league identifier.
        base_season: The current season year (e.g., "2024").
        draft_rounds: Number of rounds in the draft.

    Returns:
        List of DraftPick objects ready for insertion.
    """
    try:
        base_year = int(base_season)
    except (TypeError, ValueError):
        return []

    if draft_rounds <= 0 or not rosters:
        return []

    draft_picks: list[DraftPick] = []
    for season_offset in range(1, 4):
        season_value = str(base_year + season_offset)
        for roster in rosters:
            for round_value in range(1, draft_rounds + 1):
                draft_picks.append(
                    DraftPick(
                        league_id=league_id,
                        season=season_value,
                        round=round_value,
                        original_roster_id=roster.roster_id,
                        current_roster_id=roster.roster_id,
                        pick_id=None,
                        source="seed",
                    )
                )

    return draft_picks


def apply_traded_picks(
    conn: sqlite3.Connection,
    raw_traded_picks: list[dict[str, Any]] | None,
    league_id: str,
) -> None:
    """Update draft pick ownership based on traded picks data.

    Takes the raw traded_picks response from the Sleeper API and updates
    the current_roster_id for each traded pick in the database.

    Args:
        conn: SQLite database connection.
        raw_traded_picks: Raw traded picks data from Sleeper API.
        league_id: The league identifier.
    """
    if not raw_traded_picks:
        return

    for pick in raw_traded_picks:
        season_value = pick.get("season")
        round_value = pick.get("round")
        original_roster_id = pick.get("roster_id")
        owner_id = pick.get("owner_id")

        if season_value is None or round_value is None or original_roster_id is None:
            continue
        if owner_id is None:
            continue

        conn.execute(
            """
            UPDATE draft_picks
            SET current_roster_id = :current_roster_id
            WHERE league_id = :league_id
              AND season = :season
              AND round = :round
              AND original_roster_id = :original_roster_id
            """,
            {
                "current_roster_id": int(owner_id),
                "league_id": league_id,
                "season": str(season_value),
                "round": int(round_value),
                "original_roster_id": int(original_roster_id),
            },
        )
