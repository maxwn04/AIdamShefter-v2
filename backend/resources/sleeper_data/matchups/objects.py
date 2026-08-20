"""Immutable current matchup resource contracts."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from backend.resources._contracts import ContractModel


class PlayerPerformance(ContractModel):
    sleeper_player_id: str
    full_name: str | None
    points: Decimal
    role: Literal["starter", "bench"]


class Matchup(ContractModel):
    season_roster_id: UUID
    sleeper_roster_id: str
    franchise_id: UUID
    franchise_name: str
    week: int
    sleeper_matchup_id: int | None
    points: Decimal
    player_performances: tuple[PlayerPerformance, ...]
    source_api_request_id: UUID
