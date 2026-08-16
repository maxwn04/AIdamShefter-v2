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
