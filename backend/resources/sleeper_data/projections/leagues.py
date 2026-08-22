"""Transaction-scoped writers for league metadata and membership."""

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.database.models.sleeper import (
    ApiRequest,
    League,
    LeagueUser,
    User,
)
from backend.resources.sleeper_data.common.codec import jsonb_expression
from backend.resources.sleeper_data.projections.common import (
    request_order,
    request_season,
)
from backend.services.datalayer.errors import DatalayerScopeConflict
from backend.services.datalayer.sleeper.endpoints.contracts import (
    LeagueEndpointRecords,
    LeagueUsersEndpointRecords,
)


def write_league(
    session: Session,
    competition_id: UUID,
    request: ApiRequest,
    records: LeagueEndpointRecords,
) -> None:
    """Upsert the competition season's league metadata in the caller transaction."""

    season = request_season(session, competition_id, request)
    record = records.league
    if record.sleeper_league_id != season.sleeper_league_id or record.season != str(
        season.season_year
    ):
        raise DatalayerScopeConflict(
            "league record does not match core season identity"
        )
    values = {
        "competition_season_id": season.id,
        "source_api_request_id": request.id,
        "name": record.name,
        "status": record.status,
        "season": record.season,
        "previous_sleeper_league_id": record.previous_sleeper_league_id,
        "sleeper_draft_id": record.sleeper_draft_id,
        "sport": record.sport,
        "scoring_settings": jsonb_expression(record.scoring_settings),
        "roster_positions": jsonb_expression(list(record.roster_positions)),
        "provider_settings": jsonb_expression(record.provider_settings),
        "playoff_start_week": record.playoff_start_week,
        "playoff_team_count": record.playoff_team_count,
        "league_average_match": record.league_average_match,
        "updated_at": sa.func.now(),
    }
    session.execute(
        pg_insert(League.__table__)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[League.competition_season_id],
            set_={
                key: value
                for key, value in values.items()
                if key != "competition_season_id"
            },
        )
    )


def write_league_users(
    session: Session,
    competition_id: UUID,
    request: ApiRequest,
    records: LeagueUsersEndpointRecords,
) -> None:
    """Replace season membership and upsert globally ordered user profiles."""

    season = request_season(session, competition_id, request)
    sleeper_user_ids = [row.sleeper_user_id for row in records.users]
    existing_users = {
        row[0].sleeper_user_id: (row[0], row[1])
        for row in session.execute(
            sa.select(User, ApiRequest)
            .join(ApiRequest, ApiRequest.id == User.source_api_request_id)
            .where(User.sleeper_user_id.in_(sleeper_user_ids))
        )
    }
    for record in records.users:
        existing = existing_users.get(record.sleeper_user_id)
        existing_order = None if existing is None else request_order(existing[1])
        if existing_order is not None and request_order(request) < existing_order:
            continue
        values = {
            "sleeper_user_id": record.sleeper_user_id,
            "display_name": record.display_name,
            "username": record.username,
            "avatar": record.avatar,
            "metadata": jsonb_expression(record.metadata),
            "source_api_request_id": request.id,
            "updated_at": sa.func.now(),
        }
        session.execute(
            pg_insert(User.__table__)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[User.sleeper_user_id],
                set_={
                    key: value
                    for key, value in values.items()
                    if key != "sleeper_user_id"
                },
            )
        )

    user_ids = {row.sleeper_user_id for row in records.users}
    if any(row.sleeper_user_id not in user_ids for row in records.league_users):
        raise DatalayerScopeConflict("league-local user is missing its global profile")
    session.execute(
        sa.delete(LeagueUser).where(LeagueUser.competition_season_id == season.id)
    )
    for record in records.league_users:
        session.execute(
            sa.insert(LeagueUser.__table__).values(
                competition_season_id=season.id,
                sleeper_user_id=record.sleeper_user_id,
                team_name=record.team_name,
                nickname=record.nickname,
                is_commissioner=record.is_commissioner,
                metadata=jsonb_expression(record.metadata),
                source_api_request_id=request.id,
            )
        )
