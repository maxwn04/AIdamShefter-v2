"""Immutable Sleeper league-season read contracts."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field, StrictBool, model_validator

from backend.resources._contracts import ContractModel
from backend.services.datalayer.canonical_json import JsonValue


class RefreshSeasonIdentity(ContractModel):
    """Core season identity needed before Sleeper facts have been loaded."""

    competition_id: UUID
    competition_season_id: UUID
    sleeper_league_id: str
    season_year: int = Field(strict=True, ge=1900, le=9999)


class SnapshotSeasonIdentity(ContractModel):
    competition_id: UUID
    competition_season_id: UUID
    sleeper_league_id: str
    season_year: int = Field(strict=True, ge=1900, le=9999)
    sequence_number: int = Field(strict=True, ge=1)


class SnapshotLineage(ContractModel):
    primary_competition_season_id: UUID
    primary_is_latest: StrictBool
    seasons: tuple[SnapshotSeasonIdentity, ...]

    @model_validator(mode="after")
    def validate_lineage(self) -> "SnapshotLineage":
        if not self.seasons:
            raise ValueError("snapshot lineage must contain the primary season")
        if self.seasons[-1].competition_season_id != self.primary_competition_season_id:
            raise ValueError("snapshot lineage must end with the primary season")
        competition_ids = {season.competition_id for season in self.seasons}
        if len(competition_ids) != 1:
            raise ValueError("snapshot lineage must belong to one competition")
        sequences = [season.sequence_number for season in self.seasons]
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise ValueError("snapshot lineage must have unique ascending sequences")
        return self


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
