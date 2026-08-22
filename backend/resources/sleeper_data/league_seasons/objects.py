"""Immutable Sleeper league-season read contracts."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from backend.resources._contracts import ContractModel
from backend.services.datalayer.canonical_json import JsonValue


class SnapshotPlanningContext(ContractModel):
    competition_id: UUID
    competition_season_id: UUID
    sleeper_league_id: str
    season_year: int = Field(strict=True, ge=1900, le=9999)
    playoff_start_week: int | None
    playoff_team_count: int | None
    draft_rounds: int = Field(strict=True, ge=0)
    league_average_match: int | None


class LeagueSeasonOverview(ContractModel):
    competition_id: UUID
    competition_season_id: UUID
    competition_name: str
    sleeper_league_id: str
    season_year: int
    sequence_number: int
    league_name: str
    status: str | None
    scoring_settings: dict[str, JsonValue]
    roster_positions: tuple[str, ...]
    provider_settings: dict[str, JsonValue]
    playoff_start_week: int | None
    playoff_team_count: int | None
    league_average_match: int | None
    roster_count: int = Field(strict=True, ge=0)
    source_api_request_id: UUID
