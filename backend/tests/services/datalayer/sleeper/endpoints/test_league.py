from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from backend.json import JsonValue, parse_json_bytes
from backend.services.datalayer.errors import EndpointPayloadRejected
from backend.services.datalayer.sleeper.endpoints.league import (
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
from backend.sleeper import EndpointKind

_FIXTURES = Path(__file__).resolve().parents[6] / "datalayer/tests/fixtures/sleeper"
_SEASON_ID = UUID("11111111-1111-1111-1111-111111111111")


def _fixture(name: str) -> JsonValue:
    return parse_json_bytes((_FIXTURES / name).read_bytes())


def test_builds_exact_league_and_nfl_state_requests() -> None:
    league = build_league_request(
        sleeper_league_id="123",
        competition_season_id=_SEASON_ID,
    )
    state = build_nfl_state_request()

    assert league.endpoint_kind is EndpointKind.LEAGUE
    assert str(league.scope_key) == f"league:{_SEASON_ID}"
    assert league.path == "/league/123"
    assert league.parameters == {}
    assert league.week is None
    assert state.endpoint_kind is EndpointKind.NFL_STATE
    assert str(state.scope_key) == "state:nfl"
    assert state.path == "/state/nfl"


def test_normalizes_fixture_league_with_structured_exact_values() -> None:
    payload = _fixture("league.json")
    assert isinstance(payload, dict)
    scoring_settings = payload["scoring_settings"]
    assert isinstance(scoring_settings, dict)
    scoring_settings["reception_bonus"] = Decimal("0.25")

    finding = validate_league_completeness(
        payload,
        expected_sleeper_league_id="123",
    )
    record = normalize_league(
        payload,
        expected_sleeper_league_id="123",
    )

    assert finding.is_complete is True
    assert record.sleeper_league_id == "123"
    assert record.season == "2024"
    assert record.name == "Test League"
    assert record.sport == "nfl"
    assert record.scoring_settings == {
        "pass_td": 4,
        "reception_bonus": Decimal("0.25"),
    }
    assert isinstance(record.scoring_settings, dict)
    assert record.roster_positions == ("QB", "RB", "WR", "TE", "FLEX")
    assert record.provider_settings == {"draft_rounds": 2}
    assert record.playoff_start_week == 15
    assert record.playoff_team_count == 4
    assert record.draft_rounds == 2
    assert not hasattr(record, "__dict__")
    with pytest.raises(FrozenInstanceError):
        record.name = "changed"  # type: ignore[misc]


def test_normalizes_fixture_nfl_state_without_clock_inference() -> None:
    payload = _fixture("state.json")

    finding = validate_nfl_state_completeness(payload)
    record = normalize_nfl_state(payload)

    assert finding.is_complete is True
    assert record.sport == "nfl"
    assert record.season == "2024"
    assert record.week == 2
    assert record.season_type is None


def test_builds_exact_league_users_request() -> None:
    request = build_league_users_request(
        sleeper_league_id="123",
        competition_season_id=_SEASON_ID,
    )

    assert request.endpoint_kind is EndpointKind.LEAGUE_USERS
    assert str(request.scope_key) == f"users:{_SEASON_ID}"
    assert request.path == "/league/123/users"
    assert request.parameters == {}
    assert request.week is None


def test_normalizes_fixture_users_into_global_and_league_local_rows() -> None:
    payload = _fixture("users.json")

    finding = validate_league_users_completeness(payload)
    records = normalize_league_users(payload)

    assert finding.is_complete is True
    assert tuple(user.sleeper_user_id for user in records.users) == ("u1", "u2")
    assert records.users[0].display_name == "Alice"
    assert records.users[0].username is None
    assert records.users[0].avatar == "avatar1"
    assert records.users[0].metadata == {}
    assert records.league_users[0].sleeper_user_id == "u1"
    assert records.league_users[0].team_name is None
    assert records.league_users[0].nickname is None
    assert records.league_users[0].is_commissioner is False
    assert records.league_users[0].metadata == {}
    assert not hasattr(records, "__dict__")


def test_users_are_sorted_and_keep_profile_and_league_metadata_separate() -> None:
    payload: JsonValue = [
        {
            "user_id": "u2",
            "username": "second",
            "avatar": "avatar2",
            "is_owner": True,
            "profile_rating": Decimal("4.25"),
            "metadata": {"team_name": "Second Team", "nickname": "Second"},
        },
        {
            "user_id": "u1",
            "display_name": "First",
            "is_commissioner": False,
            "metadata": {"team_name": "First Team", "custom_local": True},
        },
    ]

    records = normalize_league_users(payload)

    assert tuple(user.sleeper_user_id for user in records.users) == ("u1", "u2")
    assert records.users[1].display_name == "second"
    assert records.users[1].metadata == {"profile_rating": Decimal("4.25")}
    assert records.league_users[0].team_name == "First Team"
    assert records.league_users[0].metadata == {
        "team_name": "First Team",
        "custom_local": True,
    }
    assert records.league_users[1].nickname == "Second"
    assert records.league_users[1].is_commissioner is True


@pytest.mark.parametrize(
    ("payload", "expected_id", "code"),
    [
        ([], "123", "league_payload_not_object"),
        ({"league_id": "other", "season": "2024", "name": "L", "sport": "nfl"}, "123", "league_id_mismatch"),
        ({"league_id": "123", "season": "2024", "name": "L", "sport": "nfl", "settings": []}, "123", "settings_invalid"),
    ],
)
def test_league_malformed_payload_is_incomplete_and_structurally_rejected(
    payload: JsonValue,
    expected_id: str,
    code: str,
) -> None:
    finding = validate_league_completeness(
        payload,
        expected_sleeper_league_id=expected_id,
    )

    assert finding.is_complete is False
    assert finding.code == code
    with pytest.raises(EndpointPayloadRejected) as raised:
        normalize_league(
            payload,
            expected_sleeper_league_id=expected_id,
        )
    assert raised.value.endpoint_kind is EndpointKind.LEAGUE
    assert raised.value.code == code


def test_invalid_nfl_state_is_not_treated_as_an_empty_success() -> None:
    payload: JsonValue = {"season": "2024", "week": Decimal("2.5")}

    finding = validate_nfl_state_completeness(payload)

    assert finding.is_complete is False
    assert finding.code == "week_invalid"
    with pytest.raises(EndpointPayloadRejected) as raised:
        normalize_nfl_state(payload)
    assert raised.value.endpoint_kind is EndpointKind.NFL_STATE
    assert raised.value.code == "week_invalid"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({}, "league_users_payload_not_array"),
        (["not-an-object"], "league_user_not_object"),
        ([{"display_name": "Missing ID"}], "league_user_id_missing"),
        (
            [
                {"user_id": "u1", "display_name": "One"},
                {"user_id": "u1", "display_name": "Again"},
            ],
            "duplicate_league_user",
        ),
        ([{"user_id": "u1"}], "league_user_display_name_missing"),
        (
            [{"user_id": "u1", "display_name": "One", "metadata": []}],
            "user_metadata_invalid",
        ),
        (
            [{"user_id": "u1", "display_name": "One", "is_owner": 1}],
            "league_user_commissioner_invalid",
        ),
    ],
)
def test_malformed_league_users_are_incomplete_and_structurally_rejected(
    payload: JsonValue,
    code: str,
) -> None:
    finding = validate_league_users_completeness(payload)

    assert finding.is_complete is False
    assert finding.code == code
    with pytest.raises(EndpointPayloadRejected) as raised:
        normalize_league_users(payload)
    assert raised.value.endpoint_kind is EndpointKind.LEAGUE_USERS
    assert raised.value.code == code
