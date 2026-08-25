from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from backend.services.datalayer.canonical_json import parse_json_bytes
from backend.services.datalayer.errors import EndpointPayloadRejected
from backend.services.datalayer.sleeper.endpoints import (
    build_matchups_request,
    build_transactions_request,
    normalize_matchups,
    normalize_transactions,
    validate_matchups_completeness,
    validate_transactions_completeness,
)
from backend.services.datalayer.sleeper.responses import EndpointRequest
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


SEASON_ID = UUID("10000000-0000-0000-0000-000000000001")
FIXTURE_ROOT = (
    Path(__file__).resolve().parents[4] / "datalayer" / "tests" / "fixtures" / "sleeper"
)


def _fixture(name: str) -> Any:
    return parse_json_bytes((FIXTURE_ROOT / f"{name}.json").read_bytes())


def test_weekly_family_builds_canonical_requests() -> None:
    matchups = build_matchups_request(SEASON_ID, "123", 8)
    transactions = build_transactions_request(SEASON_ID, "123", 8)

    assert (matchups.endpoint_kind, str(matchups.scope_key), matchups.path) == (
        EndpointKind.MATCHUPS,
        f"matchups:{SEASON_ID}:8",
        "/league/123/matchups/8",
    )
    assert (
        transactions.endpoint_kind,
        str(transactions.scope_key),
        transactions.path,
    ) == (
        EndpointKind.TRANSACTIONS,
        f"transactions:{SEASON_ID}:8",
        "/league/123/transactions/8",
    )
    assert matchups.week == transactions.week == 8


@pytest.mark.parametrize("week", [True, 0, 19])
def test_weekly_requests_reject_invalid_weeks(week: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 18"):
        build_matchups_request(SEASON_ID, "123", week)


def test_weekly_validator_rejects_scope_week_mismatch() -> None:
    request = EndpointRequest(
        endpoint_kind=EndpointKind.MATCHUPS,
        scope_key=ScopeKey.from_parts(EndpointKind.MATCHUPS, SEASON_ID, 7),
        path="/league/123/matchups/8",
        week=8,
    )

    with pytest.raises(ValueError, match="canonical matchups"):
        validate_matchups_completeness([], request)


def test_matchup_fixture_preserves_exact_points_and_lineups() -> None:
    request = build_matchups_request(SEASON_ID, "123", 1)
    records = normalize_matchups(_fixture("matchups_week1"), request)

    assert records.matchups[0].points == Decimal("100.5")
    assert [
        (row.sleeper_roster_id, row.sleeper_player_id, row.points, row.role)
        for row in records.player_performances
    ] == [
        ("1", "p1", Decimal("60.5"), "starter"),
        ("1", "p2", Decimal("40.0"), "bench"),
        ("2", "p3", Decimal("55.0"), "starter"),
        ("2", "p4", Decimal("35.0"), "bench"),
    ]


def test_matchup_ignores_sleeper_zero_starter_placeholders() -> None:
    payload = [
        {
            "roster_id": 1,
            "players": ["p1", "p2"],
            "starters": ["p1", "0", "0"],
            "players_points": {"p1": 12, "p2": 4},
        }
    ]
    request = build_matchups_request(SEASON_ID, "123", 3)

    assert validate_matchups_completeness(payload, request).is_complete
    records = normalize_matchups(payload, request)

    assert [
        (row.sleeper_player_id, row.role)
        for row in records.player_performances
    ] == [("p1", "starter"), ("p2", "bench")]


def test_matchups_are_deterministic_and_empty_week_is_authoritative() -> None:
    payload = _fixture("matchups_week1")
    assert isinstance(payload, list)
    request = build_matchups_request(SEASON_ID, "123", 1)

    assert normalize_matchups(payload, request) == normalize_matchups(
        list(reversed(payload)), request
    )
    assert normalize_matchups([], request).matchups == ()
    assert validate_matchups_completeness([], request).is_complete


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({}, "matchups_payload_not_list"),
        ([None], "matchup_not_object"),
        ([{}], "matchup_roster_id_missing"),
        ([{"roster_id": 1, "points": 1.5}], "matchup_points_invalid"),
        (
            [{"roster_id": 1, "players": ["p1"], "starters": ["p2"]}],
            "matchup_starter_not_player",
        ),
        (
            [{"roster_id": 1, "players": ["p1"], "players_points": {"p2": 1}}],
            "matchup_points_player_unknown",
        ),
    ],
)
def test_malformed_matchup_scope_is_incomplete_and_rejected(
    payload: Any,
    reason: str,
) -> None:
    request = build_matchups_request(SEASON_ID, "123", 1)
    finding = validate_matchups_completeness(payload, request)

    assert (finding.is_complete, finding.reason) == (False, reason)
    with pytest.raises(EndpointPayloadRejected) as error:
        normalize_matchups(payload, request)
    assert error.value.code == reason


def test_transaction_fixtures_emit_deterministic_semantic_moves() -> None:
    waiver = normalize_transactions(
        _fixture("transactions_week1"),
        build_transactions_request(SEASON_ID, "123", 1),
    )
    trade = normalize_transactions(
        _fixture("transactions_week2"),
        build_transactions_request(SEASON_ID, "123", 2),
    )

    assert waiver.transactions[0].sleeper_transaction_id == "tx1"
    assert waiver.transactions[0].settings == {"waiver_bid": 5}
    assert [
        (
            row.move_index,
            row.move_kind,
            row.from_sleeper_roster_id,
            row.to_sleeper_roster_id,
            row.sleeper_player_id,
            row.budget_amount,
        )
        for row in waiver.moves
    ] == [
        (0, "player", None, "1", "p2", 5),
        (1, "player", "2", None, "p3", 5),
    ]
    assert len(trade.moves) == 1
    pick = trade.moves[0]
    assert (
        pick.move_kind,
        pick.from_sleeper_roster_id,
        pick.to_sleeper_roster_id,
        pick.draft_season_year,
        pick.draft_round,
        pick.original_sleeper_roster_id,
        pick.sleeper_pick_id,
    ) == ("pick", "1", "2", 2025, 1, "1", "pick1")


def test_player_trade_combines_add_and_drop_and_zero_bid_is_preserved() -> None:
    payload = [
        {
            "transaction_id": "tx-player",
            "type": "trade",
            "settings": {"waiver_bid": 0, "price": 10},
            "adds": {"p1": 2},
            "drops": {"p1": 1},
        }
    ]
    records = normalize_transactions(
        payload, build_transactions_request(SEASON_ID, "123", 2)
    )

    assert len(records.moves) == 1
    move = records.moves[0]
    assert (move.from_sleeper_roster_id, move.to_sleeper_roster_id) == ("1", "2")
    assert move.budget_amount == 0


def test_empty_transactions_are_authoritative() -> None:
    request = build_transactions_request(SEASON_ID, "123", 8)

    assert normalize_transactions([], request).transactions == ()
    assert validate_transactions_completeness([], request).is_complete


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({}, "transactions_payload_not_list"),
        ([{}], "transaction_id_missing"),
        (
            [{"transaction_id": "tx", "draft_picks": [{"season": 2025, "round": 1}]}],
            "transaction_pick_roster_invalid",
        ),
        (
            [{"transaction_id": "tx", "settings": {"waiver_bid": -1}}],
            "transaction_budget_invalid",
        ),
    ],
)
def test_malformed_transaction_scope_is_incomplete_and_rejected(
    payload: Any,
    reason: str,
) -> None:
    request = build_transactions_request(SEASON_ID, "123", 1)
    finding = validate_transactions_completeness(payload, request)

    assert (finding.is_complete, finding.reason) == (False, reason)
    with pytest.raises(EndpointPayloadRejected) as error:
        normalize_transactions(payload, request)
    assert error.value.code == reason
