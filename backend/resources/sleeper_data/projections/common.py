"""Shared transaction-scoped lookup helpers for normalized projections."""

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.database.models.core import CompetitionSeason, SeasonRoster
from backend.database.models.sleeper import (
    ApiRequest,
    Player,
    User,
)
from backend.services.datalayer.errors import (
    DatalayerResourceNotFound,
    DatalayerScopeConflict,
)


def request_order(request: ApiRequest) -> tuple[datetime, int]:
    return request.requested_at, request.id.int


def require_season(
    session: Session,
    competition_id: UUID,
    season_id: UUID,
) -> CompetitionSeason:
    season = session.scalar(
        sa.select(CompetitionSeason).where(
            CompetitionSeason.id == season_id,
            CompetitionSeason.competition_id == competition_id,
        )
    )
    if season is None:
        raise DatalayerResourceNotFound("competition_season", str(season_id))
    return season


def request_season(
    session: Session,
    competition_id: UUID,
    request: ApiRequest,
) -> CompetitionSeason:
    if request.competition_season_id is None:
        raise DatalayerScopeConflict("endpoint requires a competition season")
    return require_season(session, competition_id, request.competition_season_id)


def season_roster_identities(
    session: Session,
    competition_id: UUID,
    request: ApiRequest,
) -> tuple[CompetitionSeason, dict[str, SeasonRoster]]:
    season = request_season(session, competition_id, request)
    rows = session.scalars(
        sa.select(SeasonRoster).where(
            SeasonRoster.competition_season_id == season.id,
            SeasonRoster.competition_id == competition_id,
        )
    ).all()
    return season, {row.sleeper_roster_id: row for row in rows}


def request_week(request: ApiRequest) -> int:
    if request.week is None:
        raise DatalayerScopeConflict("weekly endpoint is missing its week")
    return request.week


def require_users(session: Session, user_ids: Iterable[str]) -> None:
    required = set(user_ids)
    if not required:
        return
    found = set(
        session.scalars(
            sa.select(User.sleeper_user_id).where(User.sleeper_user_id.in_(required))
        )
    )
    if found != required:
        raise DatalayerScopeConflict("normalized scope references unknown users")


def require_players(session: Session, player_ids: Iterable[str]) -> None:
    required = set(player_ids)
    if not required:
        return
    found = set(
        session.scalars(
            sa.select(Player.sleeper_player_id).where(
                Player.sleeper_player_id.in_(required)
            )
        )
    )
    if found != required:
        raise DatalayerScopeConflict("normalized scope references unknown players")


def optional_identity(
    identities: dict[str, SeasonRoster],
    sleeper_roster_id: str | None,
) -> SeasonRoster | None:
    if sleeper_roster_id is None:
        return None
    identity = identities.get(sleeper_roster_id)
    if identity is None:
        raise DatalayerScopeConflict("normalized scope references an unmapped roster")
    return identity
