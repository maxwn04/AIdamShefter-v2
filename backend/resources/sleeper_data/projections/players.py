"""Transaction-scoped writer for the global Sleeper player catalog."""

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.database.models.sleeper import ApiRequest, Player
from backend.resources.sleeper_data.common.codec import jsonb_expression
from backend.services.datalayer.errors import DatalayerScopeConflict
from backend.services.datalayer.sleeper.endpoints.contracts import (
    PlayerCatalogEndpointRecords,
)


def write_players(
    session: Session,
    competition_id: UUID,
    request: ApiRequest,
    records: PlayerCatalogEndpointRecords,
) -> None:
    """Upsert observed players without deleting omitted catalog entries."""

    del competition_id
    if request.competition_season_id is not None:
        raise DatalayerScopeConflict("player catalog request must be global")
    for record in records.players:
        values = {
            "sleeper_player_id": record.sleeper_player_id,
            "full_name": record.full_name,
            "position": record.position,
            "nfl_team": record.nfl_team,
            "active": record.active,
            "status": record.status,
            "injury_status": record.injury_status,
            "age": record.age,
            "years_experience": record.years_experience,
            "metadata": jsonb_expression(record.metadata),
            "source_api_request_id": request.id,
            "updated_at": sa.func.now(),
        }
        session.execute(
            pg_insert(Player.__table__)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[Player.sleeper_player_id],
                set_={
                    key: value
                    for key, value in values.items()
                    if key != "sleeper_player_id"
                },
            )
        )
