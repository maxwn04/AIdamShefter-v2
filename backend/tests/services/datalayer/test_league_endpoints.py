from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from backend.services.datalayer.errors import EndpointPayloadRejected
from backend.services.datalayer.sleeper.endpoints import (
    build_league_request,
    build_league_users_request,
    build_nfl_state_request,
    normalize_league,
    normalize_league_users,
    normalize_nfl_state,
    validate_league_completeness,
    validate_league_users_completeness,
    validate_nfl_state_completeness,
)
from backend.services.datalayer.sleeper.responses import EndpointRequest
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


SEASON_ID = UUID("10000000-0000-0000-0000-000000000001")
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


def _fixture(name: str) -> Any:
    return json.loads(
        (FIXTURE_ROOT / f"{name}.json").read_text(encoding="utf-8"),
        parse_float=Decimal,
    )


def _golden_tables() -> dict[str, list[dict[str, Any]]]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))["tables"]


def test_league_family_builds_canonical_requests() -> None:
    league = build_league_request(SEASON_ID, "123")
    users = build_league_users_request(SEASON_ID, "123")
    state = build_nfl_state_request("nfl")

    assert (league.endpoint_kind, str(league.scope_key), league.path) == (
        EndpointKind.LEAGUE,
        f"league:{SEASON_ID}",
        "/league/123",
    )
    assert (users.endpoint_kind, str(users.scope_key), users.path) == (
        EndpointKind.LEAGUE_USERS,
        f"league_users:{SEASON_ID}",
        "/league/123/users",
    )
    assert (state.endpoint_kind, str(state.scope_key), state.path) == (
        EndpointKind.NFL_STATE,
        "nfl_state:nfl",
        "/state/nfl",
    )
    for request in (league, users, state):
        assert request.parameters == {}
        assert request.week is None
        assert request.bracket_kind is None


@pytest.mark.parametrize("league_id", ["", "../123", "123/users", "has space"])
def test_league_requests_reject_unsafe_provider_ids(league_id: str) -> None:
    with pytest.raises(ValueError):
        build_league_request(SEASON_ID, league_id)


def test_league_requests_require_a_uuid_season_scope() -> None:
    with pytest.raises(TypeError, match="must be a UUID"):
        build_league_request("season", "123")  # type: ignore[arg-type]


def test_global_request_rejects_non_nfl_sport() -> None:
    with pytest.raises(ValueError, match="only the nfl"):
        build_nfl_state_request("nba")


def test_completeness_rejects_noncanonical_request_metadata() -> None:
    invalid = EndpointRequest(
        endpoint_kind=EndpointKind.LEAGUE,
        scope_key=ScopeKey.from_parts(EndpointKind.LEAGUE, SEASON_ID),
        path="/league/123",
        week=8,
    )

    with pytest.raises(ValueError, match="canonical league request"):
        validate_league_completeness(_fixture("league"), invalid)


def test_league_fixture_is_complete_and_matches_legacy_normalization() -> None:
    payload = _fixture("league")
    payload["scoring_settings"]["reception"] = Decimal("0.50")
    payload.update(
        {
            "status": "in_season",
            "previous_league_id": "122",
            "draft_id": "draft-123",
        }
    )
    request = build_league_request(SEASON_ID, "123")

    finding = validate_league_completeness(payload, request)
    record = normalize_league(payload, request).league
    legacy = _golden_tables()["leagues"][0]

    assert finding.is_complete is True
    assert record.sleeper_league_id == legacy["league_id"]
    assert record.name == legacy["name"]
    assert record.season == legacy["season"]
    assert record.sport == legacy["sport"]
    assert record.roster_positions == tuple(json.loads(legacy["roster_positions_json"]))
    assert record.playoff_start_week == legacy["playoff_week_start"]
    assert record.playoff_team_count == legacy["playoff_teams"]
    assert record.scoring_settings["pass_td"] == 4
    assert record.scoring_settings["reception"] == Decimal("0.50")
    assert record.status == "in_season"
    assert record.previous_sleeper_league_id == "122"
    assert record.sleeper_draft_id == "draft-123"


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ([], "league_payload_not_object"),
        ({}, "league_payload_empty"),
        ({"league_id": "wrong"}, "league_identity_mismatch"),
        (
            {
                "league_id": "123",
                "name": "League",
                "season": "2024",
                "sport": "nfl",
                "settings": {},
                "scoring_settings": {},
                "roster_positions": ["QB", 1],
            },
            "league_roster_positions_invalid",
        ),
    ],
)
def test_league_completeness_rejects_malformed_payloads(
    payload: Any,
    reason: str,
) -> None:
    request = build_league_request(SEASON_ID, "123")

    finding = validate_league_completeness(payload, request)

    assert finding.is_complete is False
    assert finding.reason == reason
    with pytest.raises(EndpointPayloadRejected) as error:
        normalize_league(payload, request)
    assert error.value.code == reason


def test_league_users_fixture_matches_legacy_and_empty_is_authoritative() -> None:
    payload = list(reversed(_fixture("users")))
    payload[0]["metadata"] = {"team_name": "Beta", "nickname": "B"}
    payload[0]["is_owner"] = True
    request = build_league_users_request(SEASON_ID, "123")

    records = normalize_league_users(payload, request)
    legacy_by_id = {row["user_id"]: row for row in _golden_tables()["users"]}

    assert validate_league_users_completeness([], request).is_complete is True
    assert [record.sleeper_user_id for record in records.users] == ["u1", "u2"]
    for record in records.users:
        legacy = legacy_by_id[record.sleeper_user_id]
        assert record.display_name == legacy["display_name"]
        assert record.avatar == legacy["avatar"]
    assert records.league_users[1].team_name == "Beta"
    assert records.league_users[1].nickname == "B"
    assert records.league_users[1].is_commissioner is True


def test_league_user_display_name_falls_back_to_username() -> None:
    request = build_league_users_request(SEASON_ID, "123")
    payload = [{"user_id": "u1", "username": "fallback", "metadata": None}]

    records = normalize_league_users(payload, request)

    assert records.users[0].display_name == "fallback"
    assert records.users[0].metadata == {}
    assert records.league_users[0].metadata == {}


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({}, "league_users_payload_not_list"),
        ([None], "league_user_not_object"),
        ([{"display_name": "Missing ID"}], "league_user_id_missing"),
        (
            [
                {"user_id": "u1", "display_name": "One"},
                {"user_id": "u1", "display_name": "Duplicate"},
            ],
            "league_user_id_duplicate",
        ),
        (
            [{"user_id": "u1", "display_name": "One", "is_owner": 1}],
            "league_user_commissioner_invalid",
        ),
    ],
)
def test_league_user_completeness_rejects_one_malformed_entry(
    payload: Any,
    reason: str,
) -> None:
    finding = validate_league_users_completeness(
        payload,
        build_league_users_request(SEASON_ID, "123"),
    )

    assert finding.is_complete is False
    assert finding.reason == reason


def test_nfl_state_fixture_normalizes_complete_provenance() -> None:
    payload = _fixture("state")
    payload.update({"leg": 2, "display_week": 3, "season_type": "regular"})
    request = build_nfl_state_request()

    finding = validate_nfl_state_completeness(payload, request)
    state = normalize_nfl_state(payload, request).state

    assert finding.is_complete is True
    assert (state.sport, state.season, state.week, state.leg) == (
        "nfl",
        "2024",
        2,
        2,
    )
    assert state.display_week == 3
    assert state.provider_state == payload


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ([], "nfl_state_payload_not_object"),
        ({}, "nfl_state_payload_empty"),
        ({"week": 2}, "nfl_state_season_missing"),
        ({"season": "2024", "week": True}, "nfl_state_week_invalid"),
    ],
)
def test_nfl_state_rejects_incomplete_payloads(payload: Any, reason: str) -> None:
    finding = validate_nfl_state_completeness(payload, build_nfl_state_request())

    assert finding.is_complete is False
    assert finding.reason == reason
