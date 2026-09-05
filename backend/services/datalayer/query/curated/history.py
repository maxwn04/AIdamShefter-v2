"""Cross-season league and durable-franchise history queries."""

from __future__ import annotations

import sqlite3
from typing import Any
from uuid import UUID

from backend.services.datalayer.query.contracts import SnapshotSeason
from backend.services.datalayer.query.curated._helpers import (
    fetch_all,
    fetch_one,
    format_record,
)
from backend.services.datalayer.query.curated.league import get_standings
from backend.services.datalayer.query.identity import (
    AmbiguousRosterIdentity,
    ResolvedRosterIdentity,
    resolve_roster_identity,
)


def get_league_history(
    connection: sqlite3.Connection,
    seasons: tuple[SnapshotSeason, ...],
) -> dict[str, Any]:
    """Return deterministic cutoff summaries for every included season."""

    summaries: list[dict[str, Any]] = []
    for season in seasons:
        league = fetch_one(
            connection,
            "SELECT name FROM leagues WHERE league_id = :league_id "
            "AND season = :season",
            {
                "league_id": season.sleeper_league_id,
                "season": str(season.season_year),
            },
        )
        roster_count = fetch_one(
            connection,
            "SELECT COUNT(*) AS team_count FROM rosters "
            "WHERE league_id = :league_id",
            {"league_id": season.sleeper_league_id},
        )
        standings = get_standings(
            connection,
            season.sleeper_league_id,
            str(season.season_year),
            season.through_week,
        )
        summaries.append(
            {
                "competition_season_id": str(season.competition_season_id),
                "sleeper_league_id": season.sleeper_league_id,
                "season": season.season_year,
                "sequence_number": season.sequence_number,
                "role": season.role,
                "through_week": season.through_week,
                "league_name": (league or {}).get("name"),
                "team_count": (roster_count or {}).get("team_count", 0),
                "standings": standings.get("standings", []),
            }
        )
    primary = next(season for season in seasons if season.role == "primary")
    return {
        "found": True,
        "competition_id": str(primary.competition_id),
        "primary_season": primary.season_year,
        "seasons": summaries,
    }


def get_franchise_history(
    connection: sqlite3.Connection,
    seasons: tuple[SnapshotSeason, ...],
    franchise_or_primary_roster: str | int,
) -> dict[str, Any]:
    """Resolve once in the primary season, then query by durable franchise ID."""

    key = str(franchise_or_primary_roster).strip()
    franchise_id = _canonical_uuid(key)
    if franchise_id is None:
        primary = next(season for season in seasons if season.role == "primary")
        resolution = resolve_roster_identity(
            connection,
            competition_id=primary.competition_id,
            competition_season_id=primary.competition_season_id,
            league_id=primary.sleeper_league_id,
            roster_key=franchise_or_primary_roster,
        )
        if isinstance(resolution, AmbiguousRosterIdentity):
            return {
                "found": False,
                "roster_key": resolution.roster_key,
                "matches": [
                    match.model_dump(mode="json") for match in resolution.matches
                ],
            }
        if not isinstance(resolution, ResolvedRosterIdentity):
            return {"found": False, "roster_key": resolution.roster_key}
        franchise_id = resolution.identity.franchise_id

    rows = fetch_all(
        connection,
        """
        SELECT
            ri.franchise_id,
            ri.competition_season_id,
            ri.season_roster_id,
            ri.league_id,
            ri.roster_id,
            tp.team_name,
            tp.manager_name
        FROM roster_identities AS ri
        LEFT JOIN team_profiles AS tp
          ON tp.league_id = ri.league_id
         AND tp.roster_id = ri.roster_id
        WHERE ri.franchise_id = :franchise_id
        ORDER BY ri.league_id, ri.roster_id
        """,
        {"franchise_id": str(franchise_id)},
    )
    rows_by_league = {row["league_id"]: row for row in rows}
    appearances: list[dict[str, Any]] = []
    for season in seasons:
        row = rows_by_league.get(season.sleeper_league_id)
        if row is None:
            continue
        standing = fetch_one(
            connection,
            """
            SELECT wins, losses, ties, points_for, points_against, rank,
                   streak_type, streak_len
            FROM standings
            WHERE league_id = :league_id
              AND season = :season
              AND week = :week
              AND roster_id = :roster_id
            """,
            {
                "league_id": season.sleeper_league_id,
                "season": str(season.season_year),
                "week": season.through_week,
                "roster_id": row["roster_id"],
            },
        )
        appearances.append(
            {
                "competition_season_id": str(season.competition_season_id),
                "sleeper_league_id": season.sleeper_league_id,
                "season": season.season_year,
                "sequence_number": season.sequence_number,
                "role": season.role,
                "through_week": season.through_week,
                "season_roster_id": row["season_roster_id"],
                "sleeper_roster_id": str(row["roster_id"]),
                "team_name": row["team_name"],
                "manager_name": row["manager_name"],
                "standing": _standing(standing),
            }
        )
    if not appearances:
        return {"found": False, "franchise_id": str(franchise_id)}
    return {
        "found": True,
        "franchise_id": str(franchise_id),
        "seasons": appearances,
    }


def _canonical_uuid(value: str) -> UUID | None:
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError):
        return None
    return parsed if str(parsed) == value else None


def _standing(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "wins": row["wins"],
        "losses": row["losses"],
        "ties": row["ties"],
        "record": format_record(row["wins"], row["losses"], row["ties"]),
        "points_for": row["points_for"],
        "points_against": row["points_against"],
        "rank": row["rank"],
        "streak_type": row["streak_type"],
        "streak_len": row["streak_len"],
    }


__all__ = ["get_franchise_history", "get_league_history"]
