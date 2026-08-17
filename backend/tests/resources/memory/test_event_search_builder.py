from __future__ import annotations

from uuid import UUID

from backend.resources.memory.common import MemoryKind
from backend.resources.memory.events import EventContent
from backend.resources.memory.search_documents import (
    EVENT_DOCUMENT_BUILDER_VERSION,
    build_event_document,
)


SENDER_ID = UUID("11111111-1111-1111-1111-111111111111")
RECEIVER_ID = UUID("22222222-2222-2222-2222-222222222222")
PICK_ID = UUID("33333333-3333-3333-3333-333333333333")
RECEIPT_ID = UUID("44444444-4444-4444-4444-444444444444")


def _trade(*, reversed_assets: bool = False) -> EventContent:
    assets = [
        {
            "kind": "player",
            "direction": "sender_to_receiver",
            "player_id": "player-7",
        },
        {
            "kind": "draft_pick",
            "direction": "receiver_to_sender",
            "draft_pick_id": PICK_ID,
        },
        {
            "kind": "budget",
            "direction": "sender_to_receiver",
            "amount": 25,
        },
    ]
    if reversed_assets:
        assets.reverse()
    return EventContent.model_validate(
        {
            "event_type": "trade",
            "headline": "The Sharks and Owls completed a blockbuster.",
            "summary": "A star and future pick changed sides.",
            "salience": 5,
            "confidence": "source_backed",
            "status": "active",
            "details": {
                "kind": "trade",
                "sender_franchise_id": SENDER_ID,
                "receiver_franchise_id": RECEIVER_ID,
                "assets": assets,
            },
            "primary_api_request_id": RECEIPT_ID,
            "source_hints": {"provider": "Sleeper"},
        }
    )


def _matchup() -> EventContent:
    return EventContent.model_validate(
        {
            "event_type": "matchup",
            "headline": "The Sharks defeated the Owls.",
            "summary": "The rematch settled the week's top rivalry.",
            "salience": 4,
            "confidence": "inferred",
            "status": "active",
            "details": {
                "kind": "matchup",
                "winner_franchise_id": SENDER_ID,
                "loser_franchise_id": RECEIVER_ID,
                "sleeper_matchup_id": "week-9-table-2",
            },
        }
    )


def test_trade_projection_is_identity_free_and_normalizes_asset_order() -> None:
    projection = build_event_document(_trade())
    reordered = build_event_document(_trade(reversed_assets=True))

    assert projection == reordered
    assert projection.kind is MemoryKind.EVENT
    assert projection.status == "active"
    assert projection.salience == 5
    assert projection.entity_keys == (
        f"draft_pick:{PICK_ID}",
        f"franchise:{SENDER_ID}",
        f"franchise:{RECEIVER_ID}",
        "player:player-7",
    )
    assert projection.evidence_version_ids == ()
    assert projection.related_item_ids == ()
    assert projection.tags == ()
    assert projection.builder_version == EVENT_DOCUMENT_BUILDER_VERSION
    assert "event type: trade" in projection.document_text
    assert "sender_to_receiver player:player-7" in projection.document_text
    assert "receiver_to_sender draft_pick:" in projection.document_text
    assert str(RECEIPT_ID) not in projection.document_text


def test_matchup_projection_preserves_searchable_payload_details() -> None:
    projection = build_event_document(_matchup())

    assert projection.entity_keys == (
        f"franchise:{SENDER_ID}",
        f"franchise:{RECEIVER_ID}",
    )
    assert "winner: franchise:" in projection.document_text
    assert "loser: franchise:" in projection.document_text
    assert "matchup: week-9-table-2" in projection.document_text


def test_event_projection_hash_covers_complete_content_not_search_text() -> None:
    content = _trade()
    original = build_event_document(content)
    changed_receipt = build_event_document(
        content.model_copy(update={"primary_api_request_id": SENDER_ID})
    )

    assert original.document_text == changed_receipt.document_text
    assert original.content_hash != changed_receipt.content_hash
