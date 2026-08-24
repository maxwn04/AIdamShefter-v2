"""Strict transport models for competition and season routes."""

from typing import Annotated, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.resources._contracts import NonBlankStr
from backend.resources.core import (
    Competition,
    CompetitionActivitySummary,
    CompetitionOverviewPage,
    CompetitionSeason,
    CompetitionSeasonActivitySummary,
    CompetitionSeasonOverviewPage,
    CreateFranchiseTarget,
    ExistingFranchiseTarget,
    RosterMappingAssignment,
)
from backend.resources.sleeper_data import LeagueSeasonOverview
from backend.services.league import RosterMappingResult, RosterMappingView


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


class CreateFranchiseTargetBody(CompetitionApiModel):
    kind: Literal["new"] = "new"
    display_name: NonBlankStr


class ExistingFranchiseTargetBody(CompetitionApiModel):
    kind: Literal["existing"] = "existing"
    franchise_id: UUID


class RosterMappingAssignmentBody(CompetitionApiModel):
    sleeper_roster_id: NonBlankStr
    target: Annotated[
        CreateFranchiseTargetBody | ExistingFranchiseTargetBody,
        Field(discriminator="kind"),
    ]

    def to_resource(self) -> RosterMappingAssignment:
        target = self.target
        resolved = (
            CreateFranchiseTarget(display_name=target.display_name)
            if isinstance(target, CreateFranchiseTargetBody)
            else ExistingFranchiseTarget(franchise_id=target.franchise_id)
        )
        return RosterMappingAssignment(
            sleeper_roster_id=self.sleeper_roster_id,
            target=resolved,
        )


class PutRosterMappingsBody(CompetitionApiModel):
    source_api_request_id: UUID
    assignments: tuple[RosterMappingAssignmentBody, ...]

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "source_api_request_id": "4fd2ceef-0d7d-47ee-a42f-e70f78684aeb",
                    "assignments": [
                        {
                            "sleeper_roster_id": "1",
                            "target": {
                                "kind": "existing",
                                "franchise_id": (
                                    "e9c48ec7-95fe-44ed-85d6-d658f7022bd2"
                                ),
                            },
                        },
                        {
                            "sleeper_roster_id": "2",
                            "target": {
                                "kind": "new",
                                "display_name": "Expansion Team",
                            },
                        },
                    ],
                }
            ]
        },
    )


class RosterMappingResponse(CompetitionApiModel):
    mapping: RosterMappingView


class RosterMappingMutationResponse(CompetitionApiModel):
    result: RosterMappingResult
