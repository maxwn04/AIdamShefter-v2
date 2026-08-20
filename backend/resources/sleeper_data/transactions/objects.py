"""Immutable current transaction resource contracts."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from backend.resources._contracts import ContractModel
from backend.services.datalayer.canonical_json import JsonValue


class TransactionMove(ContractModel):
    move_index: int
    move_kind: Literal["player", "pick"]
    from_season_roster_id: UUID | None
    to_season_roster_id: UUID | None
    sleeper_player_id: str | None
    draft_season_year: int | None
    draft_round: int | None
    original_franchise_id: UUID | None
    sleeper_pick_id: str | None
    budget_amount: int | None


class Transaction(ContractModel):
    id: UUID
    sleeper_transaction_id: str
    competition_season_id: UUID
    week: int
    transaction_type: str
    status: str | None
    provider_created_at_ms: int | None
    settings: dict[str, JsonValue]
    metadata: dict[str, JsonValue]
    moves: tuple[TransactionMove, ...]
    source_api_request_id: UUID


class TransactionQuery(ContractModel):
    competition_season_id: UUID
    week: int | None = Field(default=None, strict=True, ge=1, le=18)
    transaction_type: str | None = None
    status: str | None = None
