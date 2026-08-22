from decimal import Decimal

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.services.datalayer.sleeper.endpoints import (
    CompletenessFinding,
    EndpointRecords,
    LeagueEndpointRecords,
    LeagueRecord,
    PlayerCatalogEndpointRecords,
    PlayerRecord,
)


def test_completeness_finding_requires_a_canonical_incomplete_reason() -> None:
    assert CompletenessFinding(is_complete=True).reason is None
    assert (
        CompletenessFinding(
            is_complete=False,
            reason="player_catalog_payload_empty",
        ).reason
        == "player_catalog_payload_empty"
    )

    with pytest.raises(ValidationError):
        CompletenessFinding(is_complete=False)
    with pytest.raises(ValidationError):
        CompletenessFinding(is_complete=True, reason="unexpected")
    with pytest.raises(ValidationError):
        CompletenessFinding(is_complete=False, reason="Not Canonical")


def test_endpoint_records_are_frozen_and_preserve_decimal_json() -> None:
    records = LeagueEndpointRecords(
        league=LeagueRecord(
            sleeper_league_id="123",
            name="League",
            season="2024",
            sport="nfl",
            scoring_settings={"reception": Decimal("0.50")},
            roster_positions=("QB",),
            provider_settings={},
        )
    )

    assert records.league.scoring_settings["reception"] == Decimal("0.50")
    with pytest.raises(ValidationError, match="frozen"):
        records.league.name = "Changed"

    with pytest.raises(ValidationError):
        PlayerRecord(sleeper_player_id="p1", age=-1, metadata={})


def test_endpoint_record_union_round_trips_by_endpoint_kind() -> None:
    records = PlayerCatalogEndpointRecords(
        players=(
            PlayerRecord(
                sleeper_player_id="p1",
                full_name="Player One",
                metadata={"score": Decimal("1.25")},
            ),
        )
    )

    result = TypeAdapter(EndpointRecords).validate_python(records.model_dump())

    assert isinstance(result, PlayerCatalogEndpointRecords)
    assert result.players[0].metadata["score"] == Decimal("1.25")
