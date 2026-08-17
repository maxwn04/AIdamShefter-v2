"""Competition-scoped validation for shared memory entity references."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import InstrumentedAttribute

from backend.database.models.core import CompetitionSeason, Franchise, SeasonRoster
from backend.database.models.sleeper import LeagueUser, Player, User
from backend.resources.memory.common.errors import (
    CrossCompetitionEntityReferenceError,
    EntityReferenceNotFoundError,
)
from backend.resources.memory.common.references import (
    FranchiseRef,
    PlayerRef,
    SeasonRef,
    SeasonRosterRef,
    SleeperUserRef,
)


RoleT = TypeVar("RoleT", bound=str)
SharedEntityRef = (
    FranchiseRef[RoleT]
    | PlayerRef[RoleT]
    | SeasonRosterRef[RoleT]
    | SeasonRef[RoleT]
    | SleeperUserRef[RoleT]
)


def validate_entity_references(
    session: Session,
    competition_id: UUID,
    references: Iterable[SharedEntityRef[RoleT]],
) -> None:
    """Validate shared entity existence and competition membership."""

    franchise_ids: list[UUID] = []
    roster_ids: list[UUID] = []
    season_ids: list[UUID] = []
    player_ids: list[str] = []
    user_ids: list[str] = []
    for reference in references:
        match reference.kind:
            case "franchise":
                franchise_ids.append(reference.id)
            case "season_roster":
                roster_ids.append(reference.id)
            case "season":
                season_ids.append(reference.id)
            case "player":
                player_ids.append(reference.id)
            case "sleeper_user":
                user_ids.append(reference.id)

    _validate_scoped_uuid_entities(
        session,
        competition_id,
        "franchise",
        Franchise.id,
        Franchise.competition_id,
        franchise_ids,
    )
    _validate_scoped_uuid_entities(
        session,
        competition_id,
        "season_roster",
        SeasonRoster.id,
        SeasonRoster.competition_id,
        roster_ids,
    )
    _validate_scoped_uuid_entities(
        session,
        competition_id,
        "season",
        CompetitionSeason.id,
        CompetitionSeason.competition_id,
        season_ids,
    )

    if player_ids:
        found_players = set(
            session.scalars(
                sa.select(Player.sleeper_player_id).where(
                    Player.sleeper_player_id.in_(set(player_ids))
                )
            )
        )
        for player_id in player_ids:
            if player_id not in found_players:
                raise EntityReferenceNotFoundError("player", player_id)

    if user_ids:
        rows = session.execute(
            sa.select(User.sleeper_user_id, CompetitionSeason.competition_id)
            .outerjoin(
                LeagueUser,
                LeagueUser.sleeper_user_id == User.sleeper_user_id,
            )
            .outerjoin(
                CompetitionSeason,
                CompetitionSeason.id == LeagueUser.competition_season_id,
            )
            .where(User.sleeper_user_id.in_(set(user_ids)))
        )
        memberships: dict[str, set[UUID]] = {}
        found_users: set[str] = set()
        for user_id, scoped_competition_id in rows:
            found_users.add(user_id)
            if scoped_competition_id is not None:
                memberships.setdefault(user_id, set()).add(scoped_competition_id)
        for user_id in user_ids:
            if user_id not in found_users:
                raise EntityReferenceNotFoundError("sleeper_user", user_id)
            if competition_id not in memberships.get(user_id, set()):
                raise CrossCompetitionEntityReferenceError(
                    "sleeper_user", user_id, competition_id
                )


def _validate_scoped_uuid_entities(
    session: Session,
    competition_id: UUID,
    entity_kind: str,
    id_column: InstrumentedAttribute[UUID],
    competition_column: InstrumentedAttribute[UUID],
    ids: list[UUID],
) -> None:
    if not ids:
        return
    rows = session.execute(
        sa.select(id_column, competition_column).where(id_column.in_(set(ids)))
    )
    found: dict[UUID, UUID] = {entity_id: scope for entity_id, scope in rows}
    for entity_id in ids:
        actual_scope = found.get(entity_id)
        if actual_scope is None:
            raise EntityReferenceNotFoundError(entity_kind, entity_id)
        if actual_scope != competition_id:
            raise CrossCompetitionEntityReferenceError(
                entity_kind, entity_id, competition_id
            )
