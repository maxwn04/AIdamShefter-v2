"""Typed stable roster identity resolution over one frozen snapshot."""

from __future__ import annotations

import sqlite3
from typing import Any, Literal, TypeAlias
from uuid import UUID

from backend.services.datalayer.query.contracts import (
    DisplayName,
    NonBlankStr,
    QueryValue,
)


class FrozenRosterIdentity(QueryValue):
    competition_id: UUID
    competition_season_id: UUID
    season_roster_id: UUID
    franchise_id: UUID
    sleeper_roster_id: NonBlankStr
    team_name: DisplayName = None
    manager_name: DisplayName = None


class ResolvedRosterIdentity(QueryValue):
    status: Literal["resolved"] = "resolved"
    roster_key: str
    identity: FrozenRosterIdentity


class AmbiguousRosterIdentity(QueryValue):
    status: Literal["ambiguous"] = "ambiguous"
    roster_key: str
    matches: tuple[FrozenRosterIdentity, ...]


class RosterIdentityNotFound(QueryValue):
    status: Literal["not_found"] = "not_found"
    roster_key: str


RosterIdentityResolution: TypeAlias = (
    ResolvedRosterIdentity | AmbiguousRosterIdentity | RosterIdentityNotFound
)


def resolve_roster_identity(
    connection: sqlite3.Connection,
    *,
    competition_id: UUID,
    competition_season_id: UUID,
    league_id: str,
    roster_key: str | int,
) -> RosterIdentityResolution:
    key = "" if roster_key is None else str(roster_key).strip()
    if not key:
        return RosterIdentityNotFound(roster_key=key)

    params: dict[str, Any] = {"league_id": league_id}
    if key.isdigit():
        roster_id = int(key)
        if roster_id < 1 or str(roster_id) != key:
            return RosterIdentityNotFound(roster_key=key)
        predicate = "ri.roster_id = :roster_id"
        params["roster_id"] = roster_id
    else:
        predicate = """
            (tp.team_name IS NOT NULL AND lower(tp.team_name) = lower(:roster_key))
            OR
            (tp.manager_name IS NOT NULL AND lower(tp.manager_name) = lower(:roster_key))
        """
        params["roster_key"] = key

    rows = connection.execute(
        f"""
        SELECT
            ri.competition_id,
            ri.competition_season_id,
            ri.season_roster_id,
            ri.franchise_id,
            ri.roster_id,
            tp.team_name,
            tp.manager_name
        FROM roster_identities AS ri
        LEFT JOIN team_profiles AS tp
          ON tp.league_id = ri.league_id
         AND tp.roster_id = ri.roster_id
        WHERE ri.league_id = :league_id
          AND ({predicate})
        ORDER BY ri.roster_id
        """,
        params,
    ).fetchall()
    matches = tuple(
        FrozenRosterIdentity(
            competition_id=competition_id,
            competition_season_id=competition_season_id,
            season_roster_id=UUID(row["season_roster_id"]),
            franchise_id=UUID(row["franchise_id"]),
            sleeper_roster_id=str(row["roster_id"]),
            team_name=row["team_name"],
            manager_name=row["manager_name"],
        )
        for row in rows
    )
    if not matches:
        return RosterIdentityNotFound(roster_key=key)
    if len(matches) > 1:
        return AmbiguousRosterIdentity(roster_key=key, matches=matches)
    return ResolvedRosterIdentity(roster_key=key, identity=matches[0])


def get_roster_identity_by_canonical_id(
    connection: sqlite3.Connection,
    *,
    competition_id: UUID,
    competition_season_id: UUID,
    league_id: str,
    franchise_id: UUID | None = None,
    season_roster_id: UUID | None = None,
) -> FrozenRosterIdentity | None:
    """Resolve one canonical roster identity without exposing it to the reporter."""

    if (franchise_id is None) == (season_roster_id is None):
        raise ValueError("provide exactly one canonical roster identifier")
    column = "franchise_id" if franchise_id is not None else "season_roster_id"
    identifier = franchise_id if franchise_id is not None else season_roster_id
    row = connection.execute(
        f"""
        SELECT
            ri.season_roster_id,
            ri.franchise_id,
            ri.roster_id,
            tp.team_name,
            tp.manager_name
        FROM roster_identities AS ri
        LEFT JOIN team_profiles AS tp
          ON tp.league_id = ri.league_id
         AND tp.roster_id = ri.roster_id
        WHERE ri.league_id = :league_id
          AND ri.{column} = :identifier
        """,
        {"league_id": league_id, "identifier": str(identifier)},
    ).fetchone()
    if row is None:
        return None
    return FrozenRosterIdentity(
        competition_id=competition_id,
        competition_season_id=competition_season_id,
        season_roster_id=UUID(row["season_roster_id"]),
        franchise_id=UUID(row["franchise_id"]),
        sleeper_roster_id=str(row["roster_id"]),
        team_name=row["team_name"],
        manager_name=row["manager_name"],
    )
