from __future__ import annotations

import hashlib
import json
from typing import Any, Final, cast

from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.events.objects import EventContent
from backend.resources.memory.events.payloads.matchup import MatchupEventPayload
from backend.resources.memory.events.payloads.trade import (
    BudgetTradeAsset,
    DraftPickTradeAsset,
    PlayerTradeAsset,
    TradeEventPayload,
)
from backend.resources.memory.search_documents.objects import (
    SearchDocumentProjection,
)


EVENT_DOCUMENT_BUILDER_VERSION: Final = 2


def build_event_document(content: EventContent) -> SearchDocumentProjection:
    """Deterministically flatten complete event content for candidate discovery."""

    entity_keys = tuple(sorted(_event_entity_keys(content)))
    text_parts = [
        content.headline,
        content.summary,
        f"event type: {content.event_type.value}",
        f"status: {content.status.value}",
        f"confidence: {content.confidence.value}",
        *_event_detail_text(content),
    ]
    if entity_keys:
        text_parts.append(f"entities: {' '.join(entity_keys)}")

    return SearchDocumentProjection(
        kind=MemoryKind.EVENT,
        status=content.status.value,
        salience=content.salience,
        entity_keys=entity_keys,
        document_text="\n".join(text_parts),
        builder_version=EVENT_DOCUMENT_BUILDER_VERSION,
        content_hash=_event_content_hash(content),
    )


def _event_entity_keys(content: EventContent) -> set[str]:
    details = content.details
    if isinstance(details, TradeEventPayload):
        keys = {
            f"franchise:{details.sender_franchise_id}",
            f"franchise:{details.receiver_franchise_id}",
        }
        for asset in details.assets:
            if isinstance(asset, PlayerTradeAsset):
                keys.add(f"player:{asset.player_id}")
            elif isinstance(asset, DraftPickTradeAsset):
                keys.add(_pick_key(asset))
                if asset.original_franchise_id is not None:
                    keys.add(f"franchise:{asset.original_franchise_id}")
        return keys
    if isinstance(details, MatchupEventPayload):
        return {
            f"franchise:{details.winner_franchise_id}",
            f"franchise:{details.loser_franchise_id}",
        }
    raise TypeError(f"unsupported event payload: {type(details).__name__}")


def _event_detail_text(content: EventContent) -> list[str]:
    details = content.details
    if isinstance(details, TradeEventPayload):
        parts = [
            f"sender: franchise:{details.sender_franchise_id}",
            f"receiver: franchise:{details.receiver_franchise_id}",
        ]
        assets = sorted(_trade_asset_text(asset) for asset in details.assets)
        parts.append(f"assets: {'; '.join(assets)}")
        return parts
    if isinstance(details, MatchupEventPayload):
        return [
            f"winner: franchise:{details.winner_franchise_id}",
            f"loser: franchise:{details.loser_franchise_id}",
            f"matchup: {details.sleeper_matchup_id}",
        ]
    raise TypeError(f"unsupported event payload: {type(details).__name__}")


def _trade_asset_text(
    asset: PlayerTradeAsset | DraftPickTradeAsset | BudgetTradeAsset,
) -> str:
    if isinstance(asset, PlayerTradeAsset):
        value = f"player:{asset.player_id}"
    elif isinstance(asset, DraftPickTradeAsset):
        value = _pick_key(asset)
    else:
        value = f"budget:{asset.amount}"
    return f"{asset.direction.value} {value}"


def _pick_key(asset: DraftPickTradeAsset) -> str:
    if asset.draft_pick_id is not None:
        return f"draft_pick:{asset.draft_pick_id}"
    return f"draft_pick_natural:{asset.season}:{asset.round}:{asset.original_franchise_id}"


def _event_content_hash(content: EventContent) -> str:
    serialized = _canonical_json(_canonical_event_content(content)).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _canonical_event_content(content: EventContent) -> dict[str, Any]:
    dumped = cast(dict[str, Any], content.model_dump(mode="json"))
    details = cast(dict[str, Any], dumped["details"])
    if details["kind"] == "trade":
        assets = cast(list[dict[str, Any]], details["assets"])
        details["assets"] = sorted(assets, key=_canonical_json)
    return {
        "memory_kind": content.memory_kind.value,
        "content": dumped,
    }


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
