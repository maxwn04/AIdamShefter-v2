"""Transaction-scoped writer for matchup current state."""

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.database.models.sleeper import (
    ApiRequest,
    Matchup,
    PlayerPerformance,
)
from backend.resources.sleeper_data.projections.common import (
    request_week,
    require_players,
    season_roster_identities,
)
from backend.services.datalayer.errors import DatalayerScopeConflict
from backend.services.datalayer.sleeper.endpoints.contracts import (
    MatchupsEndpointRecords,
)


def write_matchups(
    session: Session,
    competition_id: UUID,
    request: ApiRequest,
    records: MatchupsEndpointRecords,
) -> None:
    """Replace one exact season/week of matchups and performances."""

    season, identities = season_roster_identities(session, competition_id, request)
    week = request_week(request)
    if any(
        row.week != week for row in (*records.matchups, *records.player_performances)
    ):
        raise DatalayerScopeConflict("matchup records do not match the request week")
    for roster_id in {
        row.sleeper_roster_id
        for row in (*records.matchups, *records.player_performances)
    }:
        if roster_id not in identities:
            raise DatalayerScopeConflict("matchup references an unmapped roster")
    require_players(
        session, [row.sleeper_player_id for row in records.player_performances]
    )
    session.execute(
        sa.delete(PlayerPerformance).where(
            PlayerPerformance.competition_season_id == season.id,
            PlayerPerformance.week == week,
        )
    )
    session.execute(
        sa.delete(Matchup).where(
            Matchup.competition_season_id == season.id,
            Matchup.week == week,
        )
    )
    for record in records.matchups:
        session.add(
            Matchup(
                competition_season_id=season.id,
                week=week,
                season_roster_id=identities[record.sleeper_roster_id].id,
                sleeper_matchup_id=record.sleeper_matchup_id,
                points=record.points,
                source_api_request_id=request.id,
            )
        )
    for record in records.player_performances:
        session.add(
            PlayerPerformance(
                competition_season_id=season.id,
                week=week,
                season_roster_id=identities[record.sleeper_roster_id].id,
                sleeper_matchup_id=record.sleeper_matchup_id,
                sleeper_player_id=record.sleeper_player_id,
                points=record.points,
                role=record.role,
                source_api_request_id=request.id,
            )
        )
