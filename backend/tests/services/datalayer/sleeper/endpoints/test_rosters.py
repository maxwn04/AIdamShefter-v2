from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from backend.json import JsonValue, parse_json_bytes
from backend.services.datalayer.errors import EndpointPayloadRejected
from backend.services.datalayer.sleeper.endpoints.rosters import (
    RosterPlayerRecord,
    TradedPickRecord,
    build_rosters_request,
    build_traded_picks_request,
    normalize_rosters,
    normalize_traded_picks,
    validate_rosters_completeness,
    validate_traded_picks_completeness,
)
from backend.sleeper import EndpointKind

FIXTURES = Path(__file__).resolve().parents[6] / "datalayer/tests/fixtures/sleeper"
COMPETITION_SEASON_ID = UUID("10000000-0000-0000-0000-000000000001")


def _fixture(name: str) -> JsonValue:
    return parse_json_bytes((FIXTURES / name).read_bytes())


def test_build_rosters_request_has_canonical_scope_and_path() -> None:
    request = build_rosters_request(COMPETITION_SEASON_ID, "league-123")

    assert request.endpoint_kind is EndpointKind.LEAGUE_ROSTERS
    assert str(request.scope_key) == f"rosters:{COMPETITION_SEASON_ID}"
    assert request.path == "/league/league-123/rosters"
    assert request.parameters == {}


def test_build_traded_picks_request_has_canonical_scope_and_path() -> None:
    request = build_traded_picks_request(COMPETITION_SEASON_ID, "league-123")

    assert request.endpoint_kind is EndpointKind.TRADED_PICKS
    assert str(request.scope_key) == f"traded_picks:{COMPETITION_SEASON_ID}"
    assert request.path == "/league/league-123/traded_picks"
    assert request.parameters == {}


def test_roster_fixture_normalizes_exact_totals_managers_and_players() -> None:
    records = normalize_rosters(_fixture("rosters.json"))

    assert [row.sleeper_roster_id for row in records.rosters] == ["1", "2"]
    assert records.rosters[0].wins == 1
    assert records.rosters[0].points_for == Decimal("200.10")
    assert records.rosters[0].points_against == Decimal("180.05")
    assert [(row.sleeper_user_id, row.role) for row in records.managers] == [
        ("u1", "owner"),
        ("u2", "owner"),
    ]
    assert [
        (row.sleeper_roster_id, row.sleeper_player_id, row.role)
        for row in records.players
    ] == [
        ("1", "p1", "starter"),
        ("1", "p2", "bench"),
        ("2", "p3", "starter"),
        ("2", "p4", "bench"),
    ]


def test_roster_roles_use_priority_and_include_role_only_players() -> None:
    payload: JsonValue = [
        {
            "roster_id": 7,
            "owner_id": "owner",
            "co_owners": ["co-owner", "owner"],
            "players": ["bench", "multi"],
            "starters": ["multi", "starter-only"],
            "taxi": ["multi", "taxi-only"],
            "reserve": ["reserve-only"],
            "ir": ["ir-only"],
        }
    ]

    records = normalize_rosters(payload)

    assert records.managers[0].role == "owner"
    assert records.managers[1].role == "co_owner"
    assert records.managers[1].source_order == 1
    assert [(row.sleeper_player_id, row.role) for row in records.players] == [
        ("bench", "bench"),
        ("ir-only", "ir"),
        ("multi", "starter"),
        ("reserve-only", "reserve"),
        ("starter-only", "starter"),
        ("taxi-only", "taxi"),
    ]


def test_roster_normalization_is_deterministic_across_payload_order() -> None:
    payload = _fixture("rosters.json")
    assert isinstance(payload, list)

    assert normalize_rosters(payload) == normalize_rosters(list(reversed(payload)))


def test_complete_empty_roster_array_is_authoritative() -> None:
    finding = validate_rosters_completeness([])

    assert finding.is_complete is True
    assert normalize_rosters([]).rosters == ()


def test_traded_pick_fixture_normalizes_current_ownership() -> None:
    records = normalize_traded_picks(_fixture("traded_picks.json"))

    assert records == (
        TradedPickRecord(
            draft_season_year=2025,
            draft_round=1,
            original_sleeper_roster_id="1",
            current_owner_sleeper_roster_id="2",
            sleeper_pick_id=None,
        ),
    )
    assert "__dict__" not in dir(records[0])
    with pytest.raises(FrozenInstanceError):
        records[0].draft_round = 2  # type: ignore[misc]


def test_traded_picks_are_sorted_by_natural_coordinate() -> None:
    payload: JsonValue = [
        {"season": "2026", "round": 1, "roster_id": 1, "owner_id": 2},
        {
            "season": "2025",
            "round": 2,
            "roster_id": 10,
            "owner_id": 1,
            "draft_pick_id": "pick-10",
        },
        {"season": "2025", "round": 1, "roster_id": 2, "owner_id": 1},
    ]

    records = normalize_traded_picks(payload)

    assert [
        (row.draft_season_year, row.draft_round, row.original_sleeper_roster_id)
        for row in records
    ] == [(2025, 1, "2"), (2025, 2, "10"), (2026, 1, "1")]
    assert records[1].sleeper_pick_id == "pick-10"


def test_complete_empty_traded_pick_array_is_authoritative() -> None:
    finding = validate_traded_picks_completeness([])

    assert finding.is_complete is True
    assert normalize_traded_picks([]) == ()


def test_malformed_traded_pick_is_rejected_with_endpoint_context() -> None:
    payload: JsonValue = [
        {"season": "2025", "round": 1, "roster_id": 1, "owner_id": None}
    ]

    with pytest.raises(EndpointPayloadRejected) as caught:
        normalize_traded_picks(payload)

    assert caught.value.endpoint_kind is EndpointKind.TRADED_PICKS
    assert caught.value.code == "integer_expected"


def test_malformed_roster_fact_is_rejected_with_endpoint_context() -> None:
    payload: JsonValue = [{"roster_id": 1, "players": {"p1": True}}]

    with pytest.raises(EndpointPayloadRejected) as caught:
        normalize_rosters(payload)

    assert caught.value.endpoint_kind is EndpointKind.LEAGUE_ROSTERS
    assert caught.value.code == "identifier_list_not_array"


def test_roster_endpoint_records_are_frozen_and_slotted() -> None:
    row = RosterPlayerRecord(
        sleeper_roster_id="1",
        sleeper_player_id="p1",
        role="starter",
    )

    assert "__dict__" not in dir(row)
    with pytest.raises(FrozenInstanceError):
        row.role = "bench"  # type: ignore[misc]
