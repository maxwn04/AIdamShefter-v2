"""Immutable current roster resource contracts."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from backend.resources._contracts import ContractModel, NonBlankStr
from backend.resources.sleeper_data.players.objects import Player
from backend.services.datalayer.canonical_json import JsonValue


class RosterManagerAssignment(ContractModel):
    sleeper_user_id: str
    display_name: str
    role: Literal["owner", "co_owner"]
    source_order: int = Field(strict=True, ge=0)


class RosterPlayer(ContractModel):
    player: Player
    role: Literal["starter", "bench", "taxi", "reserve", "ir", "unknown"]


class SeasonRosterIdentity(ContractModel):
    """Stable core identity for one provider roster in a competition season."""

    competition_id: UUID
    competition_season_id: UUID
    season_roster_id: UUID
    franchise_id: UUID
    sleeper_roster_id: NonBlankStr


class SeasonRosterState(ContractModel):
    season_roster_id: UUID
    competition_season_id: UUID
    franchise_id: UUID
    sleeper_roster_id: str
    franchise_name: str
    settings: dict[str, JsonValue]
    metadata: dict[str, JsonValue]
    record_string: str | None
    wins: int
    losses: int
    ties: int
    points_for: Decimal | None
    points_against: Decimal | None
    managers: tuple[RosterManagerAssignment, ...]
    players: tuple[RosterPlayer, ...]
    source_api_request_id: UUID
