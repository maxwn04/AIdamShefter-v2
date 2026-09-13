"""Render both retained and endpoint-based trades through caller-scoped labels."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from backend.resources.memory.events.payloads.trade import (
    BudgetTradeAsset,
    DraftPickTradeAsset,
    PlayerTradeAsset,
    TradeEventPayload,
    resolve_trade_transfers,
)


def present_trade(
    details: TradeEventPayload,
    *,
    roster_label: Callable[[UUID, str], str],
    player_label: Callable[[str, str], str],
    omissions: list[str] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Use the inspected event's season-aware callbacks, including pick origins.

    Legacy semantic exports retain their sender/receiver roles and directions.
    New events name both endpoints for every asset, without assigning a global
    sender to a transaction that may involve several independent exchanges.
    """
    transfers = resolve_trade_transfers(details)
    legacy = details.sender_franchise_id is not None
    participant_ids = (
        [details.sender_franchise_id, details.receiver_franchise_id]
        if legacy else sorted(
            {endpoint for transfer in transfers for endpoint in (
                transfer.from_franchise_id, transfer.to_franchise_id,
            )}, key=str,
        )
    )
    labels = {
        franchise_id: roster_label(franchise_id, f"participants.{index}.label")
        for index, franchise_id in enumerate(participant_ids)
    }
    participants = [
        {"label": labels[franchise_id],
         "role": ("sender" if index == 0 else "receiver") if legacy else "participant"}
        for index, franchise_id in enumerate(participant_ids)
    ]
    assets = []
    for index, transfer in enumerate(transfers):
        asset = transfer.asset
        if isinstance(asset, PlayerTradeAsset):
            label = player_label(asset.player_id, f"assets.{index}.label")
        elif isinstance(asset, DraftPickTradeAsset):
            if asset.season is not None:
                original = roster_label(asset.original_franchise_id, f"assets.{index}.original_team")
                label = f"{asset.season} round {asset.round} pick (originally {original})"
            else:
                label = "Draft pick"
                if omissions is not None:
                    omissions.append(f"assets.{index}.draft_pick_label")
        elif isinstance(asset, BudgetTradeAsset):
            label = f"{asset.amount} FAAB"
        else:
            raise TypeError(f"unsupported trade asset: {asset.kind}")
        direction = asset.direction.value if legacy else (
            f"{labels[transfer.from_franchise_id]} -> {labels[transfer.to_franchise_id]}"
        )
        assets.append({"label": label, "direction": direction})
    return participants, assets
