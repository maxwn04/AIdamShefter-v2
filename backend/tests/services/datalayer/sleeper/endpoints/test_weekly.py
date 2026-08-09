from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from backend.json import JsonValue, parse_json_bytes
from backend.services.datalayer.errors import EndpointPayloadRejected
from backend.services.datalayer.sleeper.endpoints.weekly import (
    MatchupRecord,
    build_matchups_request,
    build_transactions_request,
    normalize_matchups,
    normalize_transactions,
    validate_matchups_completeness,
    validate_transactions_completeness,
)
from backend.sleeper import EndpointKind

FIXTURES = Path(__file__).resolve().parents[6] / "datalayer/tests/fixtures/sleeper"
COMPETITION_SEASON_ID = UUID("10000000-0000-0000-0000-000000000001")


def _fixture(name: str) -> JsonValue:
    return parse_json_bytes((FIXTURES / name).read_bytes())


def test_build_weekly_requests_have_canonical_scope_path_and_week() -> None:
    matchup = build_matchups_request(COMPETITION_SEASON_ID, "league-123", 8)
    transaction = build_transactions_request(COMPETITION_SEASON_ID, "league-123", 8)

    assert matchup.endpoint_kind is EndpointKind.MATCHUPS
    assert str(matchup.scope_key) == f"matchups:{COMPETITION_SEASON_ID}:8"
    assert matchup.path == "/league/league-123/matchups/8"
    assert matchup.week == 8
    assert transaction.endpoint_kind is EndpointKind.TRANSACTIONS
    assert str(transaction.scope_key) == f"transactions:{COMPETITION_SEASON_ID}:8"
    assert transaction.path == "/league/league-123/transactions/8"
    assert transaction.week == 8


def test_matchup_fixture_normalizes_exact_points_and_lineup_roles() -> None:
    records = normalize_matchups(_fixture("matchups_week1.json"), week=1)

    assert records.matchups == (
        MatchupRecord(1, "1", 1, Decimal("100.5")),
        MatchupRecord(1, "2", 1, Decimal("90.0")),
    )
    assert [
        (row.sleeper_roster_id, row.sleeper_player_id, row.points, row.role)
        for row in records.player_performances
    ] == [
        ("1", "p1", Decimal("60.5"), "starter"),
        ("1", "p2", Decimal("40.0"), "bench"),
        ("2", "p3", Decimal("55.0"), "starter"),
        ("2", "p4", Decimal("35.0"), "bench"),
    ]


def test_matchup_normalization_is_deterministic_across_payload_order() -> None:
    payload = _fixture("matchups_week1.json")
    assert isinstance(payload, list)

    assert normalize_matchups(payload, week=1) == normalize_matchups(
        list(reversed(payload)), week=1
    )


def test_transaction_fixtures_preserve_bid_and_emit_pick_transfer_once() -> None:
    waiver = normalize_transactions(_fixture("transactions_week1.json"), week=1)
    trade = normalize_transactions(_fixture("transactions_week2.json"), week=2)

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
    assert pick.move_index == 0
    assert pick.move_kind == "pick"
    assert pick.from_sleeper_roster_id == "1"
    assert pick.to_sleeper_roster_id == "2"
    assert pick.draft_season_year == 2025
    assert pick.draft_round == 1
    assert pick.original_sleeper_roster_id == "1"
    assert pick.sleeper_pick_id == "pick1"


def test_complete_empty_weekly_arrays_are_authoritative() -> None:
    assert validate_matchups_completeness([]).is_complete is True
    assert validate_transactions_completeness([]).is_complete is True
    assert normalize_matchups([], week=8).matchups == ()
    assert normalize_transactions([], week=8).transactions == ()


def test_zero_waiver_bid_is_preserved() -> None:
    payload: JsonValue = [
        {
            "transaction_id": "tx-zero",
            "type": "waiver",
            "settings": {"waiver_bid": 0, "price": 10},
            "adds": {"p1": 1},
        }
    ]

    records = normalize_transactions(payload, week=1)

    assert records.moves[0].budget_amount == 0


def test_player_trade_is_one_transfer_with_both_roster_endpoints() -> None:
    payload: JsonValue = [
        {
            "transaction_id": "tx-player-trade",
            "type": "trade",
            "adds": {"p1": 2},
            "drops": {"p1": 1},
        }
    ]

    records = normalize_transactions(payload, week=2)

    assert len(records.moves) == 1
    assert records.moves[0].move_kind == "player"
    assert records.moves[0].sleeper_player_id == "p1"
    assert records.moves[0].from_sleeper_roster_id == "1"
    assert records.moves[0].to_sleeper_roster_id == "2"


def test_malformed_matchup_points_are_rejected_instead_of_dropped() -> None:
    payload = [
        {
            "matchup_id": 1,
            "roster_id": 1,
            "points": 1.5,
            "players": [],
            "starters": [],
        }
    ]

    with pytest.raises(EndpointPayloadRejected) as caught:
        normalize_matchups(payload, week=1)  # type: ignore[arg-type]

    assert caught.value.endpoint_kind is EndpointKind.MATCHUPS
    assert caught.value.code == "decimal_expected"


def test_malformed_transaction_pick_is_rejected_instead_of_dropped() -> None:
    payload: JsonValue = [
        {
            "transaction_id": "tx-bad",
            "type": "trade",
            "draft_picks": [{"season": 2025, "round": 1}],
        }
    ]

    with pytest.raises(EndpointPayloadRejected) as caught:
        normalize_transactions(payload, week=1)

    assert caught.value.endpoint_kind is EndpointKind.TRANSACTIONS
    assert caught.value.code == "draft_pick_identity_incomplete"


def test_weekly_endpoint_records_are_frozen_and_slotted() -> None:
    row = MatchupRecord(
        week=1,
        sleeper_roster_id="1",
        sleeper_matchup_id=1,
        points=Decimal("1.25"),
    )

    assert "__dict__" not in dir(row)
    with pytest.raises(FrozenInstanceError):
        row.points = Decimal("2")  # type: ignore[misc]
