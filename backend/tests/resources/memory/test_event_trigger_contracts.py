from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.resources.memory.events import (
    EventContent,
    MatchupEventPayload,
    TradeEventPayload,
)
from backend.resources.memory.triggers import TriggerContent


def _event(details: dict[str, object], event_type: str) -> EventContent:
    return EventContent.model_validate(
        {
            "event_type": event_type,
            "headline": "A consequential result",
            "summary": "The event changed the season's narrative.",
            "salience": 4,
            "confidence": "source_backed",
            "status": "active",
            "details": details,
            "primary_tool_call_id": uuid4(),
        }
    )


def test_trade_payload_discriminates_all_initial_asset_types() -> None:
    trade = _event(
        {
            "kind": "trade",
            "sender_franchise_id": uuid4(),
            "receiver_franchise_id": uuid4(),
            "assets": [
                {
                    "kind": "player",
                    "direction": "sender_to_receiver",
                    "player_id": "player-1",
                },
                {
                    "kind": "draft_pick",
                    "direction": "receiver_to_sender",
                    "draft_pick_id": uuid4(),
                },
                {
                    "kind": "budget",
                    "direction": "sender_to_receiver",
                    "amount": 10,
                },
            ],
        },
        "trade",
    )

    assert isinstance(trade.details, TradeEventPayload)
    assert [asset.kind for asset in trade.details.assets] == [
        "player",
        "draft_pick",
        "budget",
    ]

    duplicate_assets = trade.details.model_dump()
    duplicate_assets["assets"] = [
        {
            "kind": "player",
            "direction": "sender_to_receiver",
            "player_id": "player-1",
        },
        {
            "kind": "player",
            "direction": "receiver_to_sender",
            "player_id": "player-1",
        },
    ]
    with pytest.raises(ValidationError, match="assets must be distinct"):
        _event(duplicate_assets, "trade")


def test_event_contract_rejects_payload_mismatch_and_invalid_participants() -> None:
    winner_id = uuid4()
    matchup: dict[str, object] = {
        "kind": "matchup",
        "winner_franchise_id": winner_id,
        "loser_franchise_id": winner_id,
        "sleeper_matchup_id": "3",
    }
    with pytest.raises(ValidationError, match="winner and loser"):
        _event(matchup, "matchup")

    matchup["loser_franchise_id"] = uuid4()
    with pytest.raises(ValidationError, match="does not match payload kind"):
        _event(matchup, "trade")

    franchise_id = uuid4()
    with pytest.raises(ValidationError, match="sender and receiver"):
        _event(
            {
                "kind": "trade",
                "sender_franchise_id": franchise_id,
                "receiver_franchise_id": franchise_id,
                "assets": [
                    {
                        "kind": "player",
                        "direction": "sender_to_receiver",
                        "player_id": "player-1",
                    }
                ],
            },
            "trade",
        )


def test_payload_contracts_remain_independently_validatable() -> None:
    matchup = MatchupEventPayload.model_validate(
        {
            "winner_franchise_id": uuid4(),
            "loser_franchise_id": uuid4(),
            "sleeper_matchup_id": "standalone-matchup",
        }
    )
    trade = TradeEventPayload.model_validate(
        {
            "sender_franchise_id": uuid4(),
            "receiver_franchise_id": uuid4(),
            "assets": [
                {
                    "kind": "budget",
                    "direction": "sender_to_receiver",
                    "amount": 5,
                }
            ],
        }
    )

    assert matchup.kind == "matchup"
    assert trade.kind == "trade"


def test_explicit_transfer_payload_resolves_three_parties_and_preserves_legacy_json() -> None:
    from backend.resources.memory.events.payloads.trade import resolve_trade_transfers

    first, second, third = uuid4(), uuid4(), uuid4()
    explicit = TradeEventPayload.model_validate({"assets": [
        {"kind": "player", "player_id": "player-1", "from_franchise_id": first, "to_franchise_id": second},
        {"kind": "draft_pick", "season": 2027, "round": 1, "original_franchise_id": first,
         "from_franchise_id": second, "to_franchise_id": third},
        {"kind": "budget", "amount": 5, "from_franchise_id": third, "to_franchise_id": first},
    ]})
    assert [(transfer.from_franchise_id, transfer.to_franchise_id)
            for transfer in resolve_trade_transfers(explicit)] == [(first, second), (second, third), (third, first)]
    assert "sender_franchise_id" not in explicit.model_dump(mode="json")
    assert all("direction" not in asset for asset in explicit.model_dump(mode="json")["assets"])
    legacy = {"kind": "trade", "sender_franchise_id": str(first), "receiver_franchise_id": str(second),
              "assets": [{"kind": "player", "player_id": "player-1", "direction": "receiver_to_sender"}]}
    retained = TradeEventPayload.model_validate(legacy)
    assert retained.model_dump(mode="json") == legacy
    transfer, = resolve_trade_transfers(retained)
    assert (transfer.from_franchise_id, transfer.to_franchise_id) == (second, first)


@pytest.mark.parametrize("variant", ["missing_endpoint", "self_transfer", "mixed_asset", "mixed_payload", "missing_pair", "duplicate"])
def test_trade_rejects_incomplete_mixed_and_duplicate_transfers(variant: str) -> None:
    first, second = uuid4(), uuid4()
    asset = {"kind": "player", "player_id": "player-1", "from_franchise_id": first, "to_franchise_id": second}
    payload = {"assets": [asset]}
    if variant == "missing_endpoint":
        del asset["to_franchise_id"]
    elif variant == "self_transfer":
        asset["to_franchise_id"] = first
    elif variant == "mixed_asset":
        asset["direction"] = "sender_to_receiver"
    elif variant == "mixed_payload":
        payload.update(sender_franchise_id=first, receiver_franchise_id=second)
    elif variant == "missing_pair":
        payload.update(sender_franchise_id=first)
    else:
        payload["assets"].append({**asset, "from_franchise_id": second, "to_franchise_id": first})
    with pytest.raises(ValidationError):
        TradeEventPayload.model_validate(payload)


def test_trigger_contract_discriminates_initial_conditions() -> None:
    rematch = TriggerContent.model_validate(
        {
            "trigger_type": "rematch",
            "status": "open",
            "fire_policy": "one_shot",
            "target_competition_season_id": uuid4(),
            "target_week": 7,
            "condition": {
                "kind": "rematch",
                "franchise_ids": [uuid4(), uuid4()],
            },
        }
    )
    trade_evaluation = TriggerContent.model_validate(
        {
            "trigger_type": "trade_evaluation",
            "status": "open",
            "fire_policy": "until_resolved",
            "origin_event_item_id": uuid4(),
            "target_at": datetime.now(UTC),
            "condition": {"kind": "trade_evaluation"},
        }
    )

    assert rematch.condition.kind == "rematch"
    assert trade_evaluation.condition.kind == "trade_evaluation"


def test_trigger_contract_owns_condition_specific_requirements() -> None:
    with pytest.raises(ValidationError, match="target season and week"):
        TriggerContent.model_validate(
            {
                "trigger_type": "rematch",
                "status": "open",
                "fire_policy": "one_shot",
                "condition": {
                    "kind": "rematch",
                    "franchise_ids": [uuid4(), uuid4()],
                },
            }
        )

    with pytest.raises(ValidationError, match="does not match condition kind"):
        TriggerContent.model_validate(
            {
                "trigger_type": "rematch",
                "status": "open",
                "fire_policy": "one_shot",
                "origin_event_item_id": uuid4(),
                "target_week": 8,
                "condition": {"kind": "trade_evaluation"},
            }
        )
