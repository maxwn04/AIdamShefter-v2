from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest

from backend.json import JsonValue, parse_json_bytes
from backend.services.datalayer.errors import EndpointPayloadRejected
from backend.services.datalayer.sleeper.endpoints.players import (
    build_player_catalog_request,
    normalize_player_catalog,
    validate_player_catalog_completeness,
)
from backend.sleeper import EndpointKind

_FIXTURES = Path(__file__).resolve().parents[6] / "datalayer/tests/fixtures/sleeper"


def _fixture(name: str) -> JsonValue:
    return parse_json_bytes((_FIXTURES / name).read_bytes())


def test_builds_exact_global_player_catalog_request() -> None:
    request = build_player_catalog_request(sport=" NFL ")

    assert request.endpoint_kind is EndpointKind.PLAYER_CATALOG
    assert str(request.scope_key) == "players:nfl"
    assert request.path == "/players/nfl"
    assert request.parameters == {}
    assert request.week is None


def test_normalizes_fixture_catalog_in_deterministic_order_with_active_mapping() -> None:
    payload = _fixture("players.json")

    finding = validate_player_catalog_completeness(payload)
    records = normalize_player_catalog(payload)

    assert finding.is_complete is True
    assert tuple(record.sleeper_player_id for record in records) == (
        "p1",
        "p2",
        "p3",
        "p4",
    )
    first = records[0]
    assert first.full_name == "Player One"
    assert first.position == "QB"
    assert first.nfl_team == "AAA"
    assert first.active is True
    assert first.status == "Active"
    assert first.injury_status is None
    assert first.age == 25
    assert first.years_experience == 3
    assert isinstance(first.metadata, dict)
    assert first.metadata["updated_at"] == "2024-09-01"
    assert not hasattr(first, "__dict__")
    with pytest.raises(FrozenInstanceError):
        first.full_name = "changed"  # type: ignore[misc]


def test_preserves_explicit_inactive_value_and_structured_decimal_metadata() -> None:
    payload: JsonValue = {
        "z": {
            "player_id": "z",
            "first_name": "Last",
            "last_name": "Player",
            "active": False,
            "status": "Active",
            "metadata_score": Decimal("1.125"),
        },
        "a": {
            "player_id": "a",
            "full_name": "First Player",
            "status": "Retired",
        },
    }

    records = normalize_player_catalog(payload)

    assert tuple(record.sleeper_player_id for record in records) == ("a", "z")
    assert records[0].active is False
    assert records[1].full_name == "Last Player"
    assert records[1].active is False
    assert records[1].metadata["metadata_score"] == Decimal("1.125")


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ([], "player_catalog_payload_not_object"),
        ({}, "player_catalog_empty"),
        ({"p1": "not-an-object"}, "player_record_not_object"),
        ({"p1": {"player_id": "different"}}, "player_id_mismatch"),
        ({"p1": {"player_id": "p1", "age": Decimal("20.5")}}, "player_age_invalid"),
    ],
)
def test_malformed_catalog_is_incomplete_and_never_silently_drops_rows(
    payload: JsonValue,
    code: str,
) -> None:
    finding = validate_player_catalog_completeness(payload)

    assert finding.is_complete is False
    assert finding.code == code
    with pytest.raises(EndpointPayloadRejected) as raised:
        normalize_player_catalog(payload)
    assert raised.value.endpoint_kind is EndpointKind.PLAYER_CATALOG
    assert raised.value.code == code
