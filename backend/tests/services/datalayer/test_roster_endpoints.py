from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.services.datalayer.canonical_json import parse_json_bytes
from backend.services.datalayer.errors import EndpointPayloadRejected
from backend.services.datalayer.sleeper.endpoints import (
    build_league_rosters_request,
    build_traded_picks_request,
    normalize_league_rosters,
    normalize_traded_picks,
    validate_league_rosters_completeness,
    validate_traded_picks_completeness,
)
from backend.services.datalayer.sleeper.responses import EndpointRequest
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


SEASON_ID = UUID("10000000-0000-0000-0000-000000000001")
FIXTURE_ROOT = (
    Path(__file__).resolve().parents[4] / "datalayer" / "tests" / "fixtures" / "sleeper"
)


def _fixture(name: str) -> Any:
    return parse_json_bytes((FIXTURE_ROOT / f"{name}.json").read_bytes())


def test_roster_family_builds_canonical_requests() -> None:
    rosters = build_league_rosters_request(SEASON_ID, "123")
    picks = build_traded_picks_request(SEASON_ID, "123")

    assert (rosters.endpoint_kind, str(rosters.scope_key), rosters.path) == (
        EndpointKind.LEAGUE_ROSTERS,
        f"league_rosters:{SEASON_ID}",
        "/league/123/rosters",
    )
    assert (picks.endpoint_kind, str(picks.scope_key), picks.path) == (
        EndpointKind.TRADED_PICKS,
        f"traded_picks:{SEASON_ID}",
        "/league/123/traded_picks",
    )
    for request in (rosters, picks):
        assert request.parameters == {}
        assert request.week is None
        assert request.bracket_kind is None


@pytest.mark.parametrize("league_id", ["", "../123", "123/rosters", "has space"])
def test_roster_requests_reject_unsafe_provider_ids(league_id: str) -> None:
    with pytest.raises(ValueError):
        build_league_rosters_request(SEASON_ID, league_id)


def test_roster_validator_rejects_noncanonical_request_metadata() -> None:
    request = EndpointRequest(
        endpoint_kind=EndpointKind.LEAGUE_ROSTERS,
        scope_key=ScopeKey.from_parts(EndpointKind.LEAGUE_ROSTERS, SEASON_ID),
        path="/league/123/rosters",
        week=8,
    )

    with pytest.raises(ValueError, match="canonical league_rosters"):
        validate_league_rosters_completeness(_fixture("rosters"), request)


def test_roster_fixture_preserves_exact_totals_managers_and_players() -> None:
    request = build_league_rosters_request(SEASON_ID, "123")
    records = normalize_league_rosters(_fixture("rosters"), request)

    assert validate_league_rosters_completeness(
        _fixture("rosters"), request
    ).is_complete
    assert [record.sleeper_roster_id for record in records.rosters] == ["1", "2"]
    assert records.rosters[0].wins == 1
    assert records.rosters[0].points_for == Decimal("200.10")
    assert records.rosters[0].points_against == Decimal("180.05")
    assert [(record.sleeper_user_id, record.role) for record in records.managers] == [
        ("u1", "owner"),
        ("u2", "owner"),
    ]
    assert [
        (record.sleeper_roster_id, record.sleeper_player_id, record.role)
        for record in records.players
    ] == [
        ("1", "p1", "starter"),
        ("1", "p2", "bench"),
        ("2", "p3", "starter"),
        ("2", "p4", "bench"),
    ]


def test_roster_roles_prioritize_and_include_role_only_players() -> None:
    payload = [
        {
            "roster_id": 7,
            "owner_id": "owner",
            "co_owners": ["co-owner", "owner", "co-owner"],
            "players": ["bench", "multi"],
            "starters": ["multi", "starter-only"],
            "taxi": ["multi", "taxi-only"],
            "reserve": ["reserve-only"],
            "ir": ["ir-only"],
        }
    ]
    records = normalize_league_rosters(
        payload, build_league_rosters_request(SEASON_ID, "123")
    )

    assert [
        (row.sleeper_user_id, row.role, row.source_order)
        for row in records.managers
    ] == [
        ("owner", "owner", 0),
        ("co-owner", "co_owner", 1),
    ]
    assert [(row.sleeper_player_id, row.role) for row in records.players] == [
        ("bench", "bench"),
        ("ir-only", "ir"),
        ("multi", "starter"),
        ("reserve-only", "reserve"),
        ("starter-only", "starter"),
        ("taxi-only", "taxi"),
    ]


def test_roster_normalization_is_deterministic_frozen_and_accepts_empty() -> None:
    payload = _fixture("rosters")
    assert isinstance(payload, list)
    request = build_league_rosters_request(SEASON_ID, "123")

    assert normalize_league_rosters(payload, request) == normalize_league_rosters(
        list(reversed(payload)), request
    )
    empty = normalize_league_rosters([], request)
    assert empty.rosters == ()
    assert validate_league_rosters_completeness([], request).is_complete
    with pytest.raises(ValidationError, match="frozen"):
        empty.endpoint_kind = EndpointKind.LEAGUE  # type: ignore[misc]


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({}, "league_rosters_payload_not_list"),
        ([None], "league_roster_not_object"),
        ([{}], "league_roster_id_missing"),
        ([{"roster_id": 1}, {"roster_id": "1"}], "league_roster_id_duplicate"),
        ([{"roster_id": 1, "players": {"p1": True}}], "roster_players_invalid"),
    ],
)
def test_malformed_roster_scope_is_incomplete_and_rejected(
    payload: Any,
    reason: str,
) -> None:
    request = build_league_rosters_request(SEASON_ID, "123")

    finding = validate_league_rosters_completeness(payload, request)

    assert (finding.is_complete, finding.reason) == (False, reason)
    with pytest.raises(EndpointPayloadRejected) as error:
        normalize_league_rosters(payload, request)
    assert error.value.code == reason


def test_traded_pick_fixture_and_natural_order_are_preserved() -> None:
    request = build_traded_picks_request(SEASON_ID, "123")
    payload = [
        {"season": "2026", "round": 1, "roster_id": 1, "owner_id": 2},
        *_fixture("traded_picks"),
        {
            "season": "2025",
            "round": 2,
            "roster_id": 10,
            "owner_id": 1,
            "draft_pick_id": "pick-10",
        },
    ]

    records = normalize_traded_picks(payload, request)

    assert [
        (row.draft_season_year, row.draft_round, row.original_sleeper_roster_id)
        for row in records.picks
    ] == [(2025, 1, "1"), (2025, 2, "10"), (2026, 1, "1")]
    assert records.picks[0].current_owner_sleeper_roster_id == "2"
    assert records.picks[1].sleeper_pick_id == "pick-10"
    assert normalize_traded_picks([], request).picks == ()
    assert validate_traded_picks_completeness([], request).is_complete


def test_duplicate_or_incomplete_traded_pick_rejects_whole_scope() -> None:
    request = build_traded_picks_request(SEASON_ID, "123")
    duplicate = [
        {"season": 2025, "round": 1, "roster_id": 1, "owner_id": 2},
        {"season": "2025", "round": 1, "roster_id": "1", "owner_id": 3},
    ]
    incomplete_pick = [{"season": 2025, "round": 1, "roster_id": 1}]

    assert validate_traded_picks_completeness(
        duplicate, request
    ).reason == "traded_pick_coordinate_duplicate"
    assert validate_traded_picks_completeness(
        incomplete_pick, request
    ).reason == "traded_pick_owner_invalid"
