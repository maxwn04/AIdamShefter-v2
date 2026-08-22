from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
from typing import Any

import pytest

from backend.services.datalayer.canonical_json import parse_json_bytes
from backend.services.datalayer.errors import EndpointPayloadRejected
from backend.services.datalayer.sleeper.endpoints import (
    build_player_catalog_request,
    normalize_player_catalog,
    validate_player_catalog_completeness,
)
from backend.services.datalayer.sleeper.responses import EndpointRequest
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[4] / "datalayer" / "tests" / "fixtures" / "sleeper"
)
GOLDEN_PATH = (
    Path(__file__).resolve().parents[4]
    / "datalayer"
    / "tests"
    / "characterization"
    / "golden"
    / "legacy_normalized_tables.json"
)


def _players_fixture() -> dict[str, Any]:
    return json.loads(
        (FIXTURE_ROOT / "players.json").read_text(encoding="utf-8"),
        parse_float=Decimal,
    )


def _legacy_players() -> dict[str, dict[str, Any]]:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return {row["player_id"]: row for row in golden["tables"]["players"]}


def test_player_catalog_builds_canonical_global_request() -> None:
    request = build_player_catalog_request("nfl")

    assert request.endpoint_kind is EndpointKind.PLAYER_CATALOG
    assert str(request.scope_key) == "player_catalog:nfl"
    assert request.path == "/players/nfl"
    assert request.parameters == {}
    assert request.week is None
    assert request.bracket_kind is None
    with pytest.raises(ValueError, match="only the nfl"):
        build_player_catalog_request("nba")


def test_player_completeness_rejects_forbidden_request_metadata() -> None:
    invalid = EndpointRequest(
        endpoint_kind=EndpointKind.PLAYER_CATALOG,
        scope_key=ScopeKey.from_parts(EndpointKind.PLAYER_CATALOG, "nfl"),
        path="/players/nfl",
        bracket_kind="winners",
    )

    with pytest.raises(ValueError, match="canonical player_catalog request"):
        validate_player_catalog_completeness(_players_fixture(), invalid)


def test_player_fixture_is_complete_deterministic_and_matches_legacy() -> None:
    payload = _players_fixture()
    payload["p2"]["active"] = True
    payload["p2"]["projection"] = Decimal("12.50")
    request = build_player_catalog_request()

    finding = validate_player_catalog_completeness(payload, request)
    records = normalize_player_catalog(payload, request)
    legacy = _legacy_players()

    assert finding.is_complete is True
    assert [record.sleeper_player_id for record in records.players] == [
        "p1",
        "p2",
        "p3",
        "p4",
    ]
    for record in records.players:
        expected = legacy[record.sleeper_player_id]
        assert record.full_name == expected["full_name"]
        assert record.position == expected["position"]
        assert record.nfl_team == expected["nfl_team"]
        assert record.status == expected["status"]
        assert record.injury_status == expected["injury_status"]
        assert record.age == expected["age"]
        assert record.years_experience == expected["years_exp"]
    assert records.players[1].active is True
    assert records.players[1].metadata["projection"] == Decimal("12.50")


def test_player_name_falls_back_to_first_and_last_name() -> None:
    payload = {
        "p1": {
            "player_id": "p1",
            "first_name": "Player",
            "last_name": "One",
        }
    }

    record = normalize_player_catalog(
        payload,
        build_player_catalog_request(),
    ).players[0]

    assert record.full_name == "Player One"


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ([], "player_catalog_payload_not_object"),
        ({}, "player_catalog_payload_empty"),
        ({"p1": None}, "player_catalog_entry_invalid"),
        (
            {"p1": {"player_id": "different"}},
            "player_catalog_identity_mismatch",
        ),
        ({"p1": {"age": True}}, "player_catalog_age_invalid"),
        ({"p1": {"active": 1}}, "player_catalog_active_invalid"),
    ],
)
def test_player_catalog_rejects_incomplete_or_malformed_payloads(
    payload: Any,
    reason: str,
) -> None:
    request = build_player_catalog_request()
    finding = validate_player_catalog_completeness(payload, request)

    assert finding.is_complete is False
    assert finding.reason == reason
    with pytest.raises(EndpointPayloadRejected) as error:
        normalize_player_catalog(payload, request)
    assert error.value.code == reason


def test_truncated_catalog_json_is_rejected_before_completeness() -> None:
    with pytest.raises(ValueError):
        parse_json_bytes(b'{"p1":{"player_id":"p1"}')
