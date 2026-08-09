from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
from uuid import UUID

import pytest

from backend.services.datalayer.errors import EndpointPayloadRejected
from backend.services.datalayer.sleeper.endpoints.brackets import (
    BracketMatchupRecord,
    build_losers_bracket_request,
    build_winners_bracket_request,
    normalize_bracket,
    validate_bracket_completeness,
)
from backend.services.datalayer.sleeper.scope import EndpointKind

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[6] / "datalayer" / "tests" / "fixtures" / "sleeper"
)
SEASON_ID = UUID("12345678-1234-5678-1234-567812345678")


def test_constructs_winners_and_losers_requests() -> None:
    winners = build_winners_bracket_request(SEASON_ID, "league_123")
    losers = build_losers_bracket_request(SEASON_ID, "league_123")

    assert winners.endpoint_kind == EndpointKind.WINNERS_BRACKET
    assert winners.scope_key.value == f"bracket:{SEASON_ID}:winners"
    assert winners.path == "/league/league_123/winners_bracket"
    assert winners.bracket_kind == "winners"
    assert winners.week is None
    assert winners.parameters == {}

    assert losers.endpoint_kind == EndpointKind.LOSERS_BRACKET
    assert losers.scope_key.value == f"bracket:{SEASON_ID}:losers"
    assert losers.path == "/league/league_123/losers_bracket"
    assert losers.bracket_kind == "losers"


@pytest.mark.parametrize("league_id", ["", "league/123", "league?x=1", "../league"])
def test_request_rejects_unsafe_sleeper_league_id(league_id: str) -> None:
    with pytest.raises(ValueError, match="safe non-empty path segment"):
        build_winners_bracket_request(SEASON_ID, league_id)


def test_completeness_accepts_authoritative_empty_list() -> None:
    finding = validate_bracket_completeness([])

    assert finding.is_complete is True
    assert finding.code == "bracket_payload_complete"


@pytest.mark.parametrize("payload", [None, {}, "not-a-list", 1])
def test_completeness_rejects_non_list_payload(payload) -> None:
    finding = validate_bracket_completeness(payload)

    assert finding.is_complete is False
    assert finding.code == "bracket_payload_not_list"


def test_normalizes_legacy_fixture_with_progression_references() -> None:
    payload = _fixture("winners_bracket.json")

    records = normalize_bracket(payload, bracket_kind="winners")

    assert records == (
        BracketMatchupRecord(
            bracket_kind="winners",
            round=1,
            matchup_id=1,
            t1_roster_id=1,
            t2_roster_id=2,
            t1_from_matchup_id=None,
            t1_from_outcome=None,
            t2_from_matchup_id=None,
            t2_from_outcome=None,
            winner_roster_id=1,
            loser_roster_id=2,
            placement=None,
        ),
        BracketMatchupRecord(
            bracket_kind="winners",
            round=2,
            matchup_id=2,
            t1_roster_id=None,
            t2_roster_id=None,
            t1_from_matchup_id=1,
            t1_from_outcome="w",
            t2_from_matchup_id=1,
            t2_from_outcome="l",
            winner_roster_id=None,
            loser_roster_id=None,
            placement=1,
        ),
    )


def test_normalization_is_deterministic_and_records_are_frozen() -> None:
    payload = _fixture("winners_bracket.json")

    records = normalize_bracket(list(reversed(payload)), bracket_kind="winners")

    assert [(record.round, record.matchup_id) for record in records] == [(1, 1), (2, 2)]
    with pytest.raises(FrozenInstanceError):
        records[0].round = 9  # type: ignore[misc]


def test_normalizes_authoritative_empty_losers_bracket_fixture() -> None:
    assert normalize_bracket(
        _fixture("losers_bracket.json"), bracket_kind="losers"
    ) == ()


@pytest.mark.parametrize(
    "node",
    [
        {"m": 1},
        {"r": 1},
        {"r": None, "m": 1},
        {"r": 1, "m": "1"},
        {"r": 1, "m": 1, "t1": "one"},
        {"r": 1, "m": 1, "t1_from": {}},
        {"r": 1, "m": 1, "t1_from": {"w": 1, "l": 2}},
        {"r": 1, "m": 1, "t1_from": {"next": 1}},
    ],
)
def test_malformed_node_is_rejected_instead_of_silently_dropped(node) -> None:
    with pytest.raises(EndpointPayloadRejected) as exc_info:
        normalize_bracket([node], bracket_kind="winners")

    assert exc_info.value.endpoint_kind == EndpointKind.WINNERS_BRACKET
    assert exc_info.value.code == "malformed_bracket_node"
    assert "node 0" in exc_info.value.summary


def test_non_object_node_is_structured_rejection() -> None:
    with pytest.raises(EndpointPayloadRejected) as exc_info:
        normalize_bracket([None], bracket_kind="losers")

    assert exc_info.value.endpoint_kind == EndpointKind.LOSERS_BRACKET
    assert exc_info.value.code == "malformed_bracket_node"


def test_duplicate_round_matchup_is_structured_rejection() -> None:
    node = {"r": 1, "m": 1, "t1": 1, "t2": 2}

    with pytest.raises(EndpointPayloadRejected) as exc_info:
        normalize_bracket([node, node], bracket_kind="winners")

    assert exc_info.value.code == "duplicate_bracket_matchup"


def _fixture(name: str):
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
