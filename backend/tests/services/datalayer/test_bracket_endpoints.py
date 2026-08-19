from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.services.datalayer.canonical_json import parse_json_bytes
from backend.services.datalayer.errors import EndpointPayloadRejected
from backend.services.datalayer.sleeper.endpoints import (
    build_losers_bracket_request,
    build_winners_bracket_request,
    normalize_losers_bracket,
    normalize_winners_bracket,
    validate_losers_bracket_completeness,
    validate_winners_bracket_completeness,
)
from backend.services.datalayer.sleeper.responses import EndpointRequest
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


SEASON_ID = UUID("10000000-0000-0000-0000-000000000001")
FIXTURE_ROOT = (
    Path(__file__).resolve().parents[4] / "datalayer" / "tests" / "fixtures" / "sleeper"
)


def _fixture(name: str) -> Any:
    return parse_json_bytes((FIXTURE_ROOT / f"{name}.json").read_bytes())


def test_bracket_family_builds_canonical_requests() -> None:
    winners = build_winners_bracket_request(SEASON_ID, "123")
    losers = build_losers_bracket_request(SEASON_ID, "123")

    assert (winners.endpoint_kind, str(winners.scope_key), winners.path) == (
        EndpointKind.WINNERS_BRACKET,
        f"winners_bracket:{SEASON_ID}:winners",
        "/league/123/winners_bracket",
    )
    assert winners.bracket_kind == "winners"
    assert (losers.endpoint_kind, str(losers.scope_key), losers.path) == (
        EndpointKind.LOSERS_BRACKET,
        f"losers_bracket:{SEASON_ID}:losers",
        "/league/123/losers_bracket",
    )
    assert losers.bracket_kind == "losers"


def test_bracket_validator_rejects_kind_metadata_mismatch() -> None:
    request = EndpointRequest(
        endpoint_kind=EndpointKind.WINNERS_BRACKET,
        scope_key=ScopeKey.from_parts(
            EndpointKind.WINNERS_BRACKET, SEASON_ID, "winners"
        ),
        path="/league/123/winners_bracket",
        bracket_kind="losers",
    )

    with pytest.raises(ValueError, match="canonical winners_bracket"):
        validate_winners_bracket_completeness([], request)


def test_winners_fixture_preserves_nodes_and_progression() -> None:
    request = build_winners_bracket_request(SEASON_ID, "123")
    records = normalize_winners_bracket(_fixture("winners_bracket"), request)

    assert [(row.round, row.node_key) for row in records.matchups] == [
        (1, "1"),
        (2, "2"),
    ]
    first, second = records.matchups
    assert (
        first.t1_sleeper_roster_id,
        first.t2_sleeper_roster_id,
        first.winner_sleeper_roster_id,
        first.loser_sleeper_roster_id,
    ) == ("1", "2", "1", "2")
    assert (
        second.t1_from_node_key,
        second.t1_from_outcome,
        second.t2_from_node_key,
        second.t2_from_outcome,
        second.placement,
    ) == ("1", "w", "1", "l", 1)


def test_missing_matchup_id_uses_deterministic_array_position_key() -> None:
    request = build_winners_bracket_request(SEASON_ID, "123")
    payload = [
        {"r": 2, "t1_from": {"w": 1}},
        {"r": 1, "m": 1, "t1": 1, "t2": 2},
    ]

    records = normalize_winners_bracket(payload, request)

    assert [(row.round, row.node_key) for row in records.matchups] == [
        (1, "1"),
        (2, "index:0"),
    ]


def test_preplayoff_empty_brackets_are_authoritative_and_frozen() -> None:
    winners = build_winners_bracket_request(SEASON_ID, "123")
    losers = build_losers_bracket_request(SEASON_ID, "123")

    assert normalize_winners_bracket([], winners).matchups == ()
    empty_losers = normalize_losers_bracket(_fixture("losers_bracket"), losers)
    assert empty_losers.matchups == ()
    assert validate_winners_bracket_completeness([], winners).is_complete
    assert validate_losers_bracket_completeness([], losers).is_complete
    with pytest.raises(ValidationError, match="frozen"):
        empty_losers.matchups = ()  # type: ignore[misc]


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({}, "bracket_payload_not_list"),
        ([None], "bracket_node_not_object"),
        ([{"m": 1}], "bracket_round_invalid"),
        ([{"r": 1, "m": "one"}], "bracket_matchup_id_invalid"),
        ([{"r": 1, "m": 1, "t1_from": {}}], "bracket_t1_from_invalid"),
        (
            [{"r": 1, "m": 1}, {"r": 2, "m": 1}],
            "bracket_node_key_duplicate",
        ),
    ],
)
def test_malformed_bracket_scope_is_incomplete_and_rejected(
    payload: Any,
    reason: str,
) -> None:
    request = build_winners_bracket_request(SEASON_ID, "123")
    finding = validate_winners_bracket_completeness(payload, request)

    assert (finding.is_complete, finding.reason) == (False, reason)
    with pytest.raises(EndpointPayloadRejected) as error:
        normalize_winners_bracket(payload, request)
    assert error.value.code == reason
