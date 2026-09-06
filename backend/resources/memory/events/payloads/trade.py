from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from backend.resources._contracts import ContractModel, NonBlankStr


class TradeAssetDirection(StrEnum):
    SENDER_TO_RECEIVER = "sender_to_receiver"
    RECEIVER_TO_SENDER = "receiver_to_sender"


class _TradeTransfer(ContractModel):
    kind: str
    direction: TradeAssetDirection | None = Field(default=None, exclude_if=lambda value: value is None)
    from_franchise_id: UUID | None = Field(default=None, exclude_if=lambda value: value is None)
    to_franchise_id: UUID | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def validate_transfer(self) -> _TradeTransfer:
        endpoints = (self.from_franchise_id, self.to_franchise_id)
        if self.direction is not None:
            if any(value is not None for value in endpoints):
                raise ValueError("trade asset must use either legacy direction or explicit endpoints")
        elif any(value is None for value in endpoints):
            raise ValueError("trade asset requires direction or complete from/to franchise identities")
        elif self.from_franchise_id == self.to_franchise_id:
            raise ValueError("trade asset source and destination must differ")
        return self


class PlayerTradeAsset(_TradeTransfer):
    kind: Literal["player"] = "player"
    player_id: NonBlankStr


class DraftPickTradeAsset(_TradeTransfer):
    kind: Literal["draft_pick"] = "draft_pick"
    draft_pick_id: UUID | None = Field(default=None, exclude_if=lambda value: value is None)
    season: int | None = Field(default=None, ge=1900, le=9999, strict=True, exclude_if=lambda value: value is None)
    round: int | None = Field(default=None, ge=1, strict=True, exclude_if=lambda value: value is None)
    original_franchise_id: UUID | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def validate_identity(self) -> DraftPickTradeAsset:
        natural = (self.season, self.round, self.original_franchise_id)
        if self.draft_pick_id is not None:
            if any(value is not None for value in natural):
                raise ValueError("pick identity must use either canonical UUID or draft year/round/original franchise")
        elif any(value is None for value in natural):
            raise ValueError("natural pick identity requires draft year, round, and original franchise")
        return self



class BudgetTradeAsset(_TradeTransfer):
    kind: Literal["budget"] = "budget"
    amount: int = Field(ge=0, strict=True)


TradeAsset = Annotated[
    PlayerTradeAsset | DraftPickTradeAsset | BudgetTradeAsset,
    Field(discriminator="kind"),
]


class TradeEventPayload(ContractModel):
    kind: Literal["trade"] = "trade"
    sender_franchise_id: UUID | None = Field(default=None, exclude_if=lambda value: value is None)
    receiver_franchise_id: UUID | None = Field(default=None, exclude_if=lambda value: value is None)
    assets: list[TradeAsset] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_trade(self) -> TradeEventPayload:
        legacy_pair = (self.sender_franchise_id, self.receiver_franchise_id)
        if any(value is not None for value in legacy_pair):
            if any(value is None for value in legacy_pair):
                raise ValueError("legacy trade requires both sender and receiver")
            if self.sender_franchise_id == self.receiver_franchise_id:
                raise ValueError("trade sender and receiver must differ")
            if any(asset.direction is None for asset in self.assets):
                raise ValueError("legacy trade pair requires legacy directions on all assets")
        elif any(asset.direction is not None for asset in self.assets):
            raise ValueError("explicit trade requires from/to franchise identities on all assets")

        asset_keys: list[tuple[object, ...]] = []
        for asset in self.assets:
            if isinstance(asset, PlayerTradeAsset):
                asset_keys.append((asset.kind, asset.player_id))
            elif isinstance(asset, DraftPickTradeAsset):
                asset_keys.append((asset.kind, asset.draft_pick_id, asset.season,
                                   asset.round, asset.original_franchise_id))
            else:
                asset_keys.append((asset.kind, asset.direction, asset.from_franchise_id, asset.to_franchise_id))
        if len(asset_keys) != len(set(asset_keys)):
            raise ValueError("trade assets must be distinct")
        return self


@dataclass(frozen=True, slots=True)
class ResolvedTradeTransfer:
    asset: TradeAsset
    from_franchise_id: UUID
    to_franchise_id: UUID


def resolve_trade_transfers(details: TradeEventPayload) -> tuple[ResolvedTradeTransfer, ...]:
    """Resolve both retained pair/direction and explicit endpoint payloads."""
    transfers: list[ResolvedTradeTransfer] = []
    for asset in details.assets:
        if asset.direction is None:
            sender, receiver = asset.from_franchise_id, asset.to_franchise_id
        elif asset.direction is TradeAssetDirection.SENDER_TO_RECEIVER:
            sender, receiver = details.sender_franchise_id, details.receiver_franchise_id
        else:
            sender, receiver = details.receiver_franchise_id, details.sender_franchise_id
        assert sender is not None and receiver is not None
        transfers.append(ResolvedTradeTransfer(asset, sender, receiver))
    return tuple(transfers)
