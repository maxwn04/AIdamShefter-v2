from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.database.models.sleeper import ApiRequest
from backend.resources.sleeper_data.projections.players import write_players
from backend.services.datalayer.sleeper.endpoints.contracts import (
    PlayerCatalogEndpointRecords,
    PlayerRecord,
)


def test_player_catalog_upserts_in_bounded_batches() -> None:
    session = MagicMock(spec=Session)
    request = cast(
        ApiRequest,
        SimpleNamespace(id=uuid4(), competition_season_id=None),
    )
    records = PlayerCatalogEndpointRecords(
        players=tuple(
            PlayerRecord(
                sleeper_player_id=f"player-{index}",
                full_name=f"Player {index}",
                metadata={},
            )
            for index in range(501)
        )
    )

    write_players(session, uuid4(), request, records)

    assert session.execute.call_count == 2
