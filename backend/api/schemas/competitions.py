"""Strict transport models for competition and season routes."""

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.resources._contracts import NonBlankStr
from backend.resources.core import (
    Competition,
    CompetitionActivitySummary,
    CompetitionOverviewPage,
    CompetitionSeason,
    CompetitionSeasonActivitySummary,
    CompetitionSeasonOverviewPage,
)
from backend.resources.sleeper_data import LeagueSeasonOverview


class CompetitionApiModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class CreateCompetitionBody(CompetitionApiModel):
    display_name: NonBlankStr

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"display_name": "The League"}]},
    )


class PatchCompetitionBody(CompetitionApiModel):
    display_name: NonBlankStr | None = None
    archived: Literal[True] | None = None

    @model_validator(mode="after")
    def validate_exactly_one_change(self) -> "PatchCompetitionBody":
        fields = self.model_fields_set
        rename = fields == {"display_name"} and self.display_name is not None
        archive = fields == {"archived"} and self.archived is True
        if not rename and not archive:
            raise ValueError(
                "provide exactly one of display_name or archived=true"
            )
        return self

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"display_name": "Renamed League"},
                {"archived": True},
            ]
        },
    )


class CreateCompetitionSeasonBody(CompetitionApiModel):
    season_year: Annotated[int, Field(strict=True, ge=1900, le=9999)]
    sleeper_league_id: NonBlankStr

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"season_year": 2026, "sleeper_league_id": "1234567890"}
            ]
        },
    )


class CompetitionResponse(CompetitionApiModel):
    competition: Competition


class CompetitionOverviewResponse(CompetitionApiModel):
    competition: Competition
    summary: CompetitionActivitySummary


class CompetitionPageResponse(CompetitionApiModel):
    page: CompetitionOverviewPage


class CompetitionSeasonResponse(CompetitionApiModel):
    season: CompetitionSeason


class CompetitionSeasonPageResponse(CompetitionApiModel):
    page: CompetitionSeasonOverviewPage


class CompetitionSeasonDetailResponse(CompetitionApiModel):
    season: CompetitionSeason
    summary: CompetitionSeasonActivitySummary
    normalized_overview: LeagueSeasonOverview | None
