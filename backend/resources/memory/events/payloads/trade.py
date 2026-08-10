from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from backend.resources._contracts import ContractModel, NonBlankStr


class TradeAssetDirection(StrEnum):
    SENDER_TO_RECEIVER = "sender_to_receiver"
    RECEIVER_TO_SENDER = "receiver_to_sender"


class PlayerTradeAsset(ContractModel):
    kind: Literal["player"] = "player"
    direction: TradeAssetDirection
    player_id: NonBlankStr


class DraftPickTradeAsset(ContractModel):
    kind: Literal["draft_pick"] = "draft_pick"
    direction: TradeAssetDirection
    draft_pick_id: UUID


class BudgetTradeAsset(ContractModel):
    kind: Literal["budget"] = "budget"
    direction: TradeAssetDirection
    amount: int = Field(ge=0, strict=True)


TradeAsset = Annotated[
    PlayerTradeAsset | DraftPickTradeAsset | BudgetTradeAsset,
    Field(discriminator="kind"),
]


class TradeEventPayload(ContractModel):
    kind: Literal["trade"] = "trade"
    sender_franchise_id: UUID
    receiver_franchise_id: UUID
    assets: list[TradeAsset] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_trade(self) -> TradeEventPayload:
        if self.sender_franchise_id == self.receiver_franchise_id:
            raise ValueError("trade sender and receiver must differ")

        asset_keys: list[tuple[object, ...]] = []
        for asset in self.assets:
            if isinstance(asset, PlayerTradeAsset):
                asset_keys.append((asset.kind, asset.player_id))
            elif isinstance(asset, DraftPickTradeAsset):
                asset_keys.append((asset.kind, asset.draft_pick_id))
            else:
                asset_keys.append((asset.kind, asset.direction))
        if len(asset_keys) != len(set(asset_keys)):
            raise ValueError("trade assets must be distinct")
        return self
