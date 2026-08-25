"""Competition catalog and season identity HTTP routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from backend.api.dependencies.competitions import (
    get_competition_catalog_dependencies,
    get_competition_season_dependencies,
)
from backend.api.errors.core import CoreErrorResponse
from backend.api.schemas.competitions import (
    CompetitionOverviewResponse,
    CompetitionPageResponse,
    CompetitionResponse,
    CompetitionSeasonDetailResponse,
    CompetitionSeasonPageResponse,
    CompetitionSeasonResponse,
    CreateCompetitionBody,
    CreateCompetitionSeasonBody,
    PatchCompetitionBody,
    PutRosterMappingsBody,
    RosterMappingMutationResponse,
    RosterMappingResponse,
)
from backend.composition import (
    CompetitionCatalogDependencies,
    CompetitionSeasonDependencies,
)
from backend.resources.core import (
    ArchiveCompetition,
    CompetitionQuery,
    CompetitionSeasonQuery,
    CreateCompetition,
    CreateCompetitionSeason,
    RenameCompetition,
)
from backend.services.league import ReconcileRosterMappings


router = APIRouter(
    prefix="/competitions",
    tags=["competitions"],
    responses={
        404: {
            "model": CoreErrorResponse,
            "description": "The competition or scoped season was not found.",
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "competition_not_found",
                            "summary": "competition was not found",
                        }
                    }
                }
            },
        },
        409: {
            "model": CoreErrorResponse,
            "description": "The requested identity or lifecycle change conflicts.",
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "competition_season_year_exists",
                            "summary": (
                                "that season year is already attached to this "
                                "competition"
                            ),
                            "field_errors": {
                                "season_year": [
                                    "Already attached to this competition."
                                ]
                            },
                        }
                    }
                }
            },
        },
    },
)
CatalogApi = Annotated[
    CompetitionCatalogDependencies,
    Depends(get_competition_catalog_dependencies),
]
SeasonApi = Annotated[
    CompetitionSeasonDependencies,
    Depends(get_competition_season_dependencies),
]
PageLimit = Annotated[int, Query(ge=1, le=200)]
PageOffset = Annotated[int, Query(ge=0)]


@router.get("", response_model=CompetitionPageResponse)
def competition_list(
    dependencies: CatalogApi,
    include_archived: bool = False,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> CompetitionPageResponse:
    return CompetitionPageResponse(
        page=dependencies.overviews.list_competitions(
            CompetitionQuery(
                include_archived=include_archived,
                limit=limit,
                offset=offset,
            )
        )
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CompetitionResponse,
)
def create_competition(
    body: CreateCompetitionBody,
    dependencies: CatalogApi,
) -> CompetitionResponse:
    competition = dependencies.competitions.create(
        CreateCompetition(display_name=body.display_name)
    )
    return CompetitionResponse(competition=competition)


@router.get(
    "/{competition_id}",
    response_model=CompetitionOverviewResponse,
)
def competition_detail(
    competition_id: UUID,
    dependencies: CatalogApi,
) -> CompetitionOverviewResponse:
    overview = dependencies.overviews.get_competition(competition_id)
    return CompetitionOverviewResponse(
        competition=overview.competition,
        summary=overview.summary,
    )


@router.patch(
    "/{competition_id}",
    response_model=CompetitionResponse,
)
def update_competition(
    competition_id: UUID,
    body: PatchCompetitionBody,
    dependencies: CatalogApi,
) -> CompetitionResponse:
    if body.display_name is not None:
        competition = dependencies.competitions.rename(
            RenameCompetition(
                competition_id=competition_id,
                display_name=body.display_name,
            )
        )
    else:
        competition = dependencies.competitions.archive(
            ArchiveCompetition(competition_id=competition_id)
        )
    return CompetitionResponse(competition=competition)


@router.get(
    "/{competition_id}/seasons",
    response_model=CompetitionSeasonPageResponse,
)
def competition_season_list(
    competition_id: UUID,
    dependencies: SeasonApi,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> CompetitionSeasonPageResponse:
    return CompetitionSeasonPageResponse(
        page=dependencies.overviews.list_seasons(
            competition_id,
            CompetitionSeasonQuery(limit=limit, offset=offset),
        )
    )


@router.post(
    "/{competition_id}/seasons",
    status_code=status.HTTP_201_CREATED,
    response_model=CompetitionSeasonResponse,
)
def create_competition_season(
    body: CreateCompetitionSeasonBody,
    dependencies: SeasonApi,
) -> CompetitionSeasonResponse:
    season = dependencies.seasons.create(
        CreateCompetitionSeason(
            season_year=body.season_year,
            sleeper_league_id=body.sleeper_league_id,
        )
    )
    return CompetitionSeasonResponse(season=season)


@router.get(
    "/{competition_id}/seasons/{season_id}",
    response_model=CompetitionSeasonDetailResponse,
)
def competition_season_detail(
    competition_id: UUID,
    season_id: UUID,
    dependencies: SeasonApi,
) -> CompetitionSeasonDetailResponse:
    detail = dependencies.overviews.get_season(competition_id, season_id)
    return CompetitionSeasonDetailResponse(
        season=detail.season,
        summary=detail.summary,
        normalized_overview=detail.normalized_overview,
    )


@router.get(
    "/{competition_id}/seasons/{season_id}/roster-mappings",
    response_model=RosterMappingResponse,
)
def get_roster_mappings(
    season_id: UUID,
    dependencies: SeasonApi,
) -> RosterMappingResponse:
    return RosterMappingResponse(
        mapping=dependencies.roster_mappings.get_mapping(season_id)
    )


@router.put(
    "/{competition_id}/seasons/{season_id}/roster-mappings",
    response_model=RosterMappingMutationResponse,
)
def put_roster_mappings(
    season_id: UUID,
    body: PutRosterMappingsBody,
    dependencies: SeasonApi,
) -> RosterMappingMutationResponse:
    return RosterMappingMutationResponse(
        result=dependencies.roster_mappings.reconcile(
            season_id,
            ReconcileRosterMappings(
                source_api_request_id=body.source_api_request_id,
                assignments=tuple(item.to_resource() for item in body.assignments),
            ),
        )
    )


__all__ = ["router"]
