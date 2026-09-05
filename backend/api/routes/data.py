"""Sleeper refresh, normalized overview, and snapshot audit routes."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, status

from backend.api.dependencies.data import get_data_api_dependencies
from backend.api.errors.data import DataErrorResponse
from backend.api.schemas.data import (
    DataSnapshotPageResponse,
    DataSnapshotSummary,
    DataSnapshotSummaryPage,
    LeagueSeasonOverviewResponse,
    ManualRefreshBody,
    ManualRefreshResponse,
    RefreshRunPageResponse,
    RefreshRunResponse,
    SnapshotPreparationBody,
    SnapshotPreparationResponse,
    SnapshotReadinessResponse,
)
from backend.composition import DataApiDependencies
from backend.resources.sleeper_data import DataSnapshotQuery, RefreshRunQuery
from backend.services.datalayer import (
    PrepareSnapshotRequest,
    RefreshRequest,
    RefreshTrigger,
    SnapshotPreparationMode,
    SnapshotRequest,
)


router = APIRouter(
    prefix="/data/competitions/{competition_id}/seasons/{season_id}",
    tags=["data"],
    responses={
        400: {"model": DataErrorResponse, "description": "Invalid workflow input."},
        404: {
            "model": DataErrorResponse,
            "description": "The scoped data resource was not found.",
        },
        409: {
            "model": DataErrorResponse,
            "description": "The requested operation conflicts with stored data.",
        },
        422: {
            "model": DataErrorResponse,
            "description": "The request or endpoint payload was rejected.",
        },
        503: {
            "model": DataErrorResponse,
            "description": "A required datalayer dependency is unavailable.",
        },
    },
)
DataApi = Annotated[DataApiDependencies, Depends(get_data_api_dependencies)]
PageLimit = Annotated[int, Query(ge=1, le=200)]
PageOffset = Annotated[int, Query(ge=0)]
SnapshotWeek = Annotated[int, Query(ge=1, le=18)]


@router.post(
    "/refreshes",
    status_code=status.HTTP_201_CREATED,
    response_model=ManualRefreshResponse,
)
def run_manual_refresh(
    season_id: UUID,
    dependencies: DataApi,
    body: Annotated[ManualRefreshBody, Body()] = ManualRefreshBody(),
) -> ManualRefreshResponse:
    outcome = dependencies.refresh.refresh(
        RefreshRequest(
            competition_season_id=season_id,
            through_week=body.through_week,
            trigger=RefreshTrigger.MANUAL,
        )
    )
    refresh = dependencies.refreshes.get_refresh_for_season(
        season_id,
        outcome.refresh_run_id,
    )
    return ManualRefreshResponse(
        refresh=refresh,
        effective_through_week=outcome.effective_through_week,
        scope_results=outcome.scope_results,
    )


@router.get("/refreshes", response_model=RefreshRunPageResponse)
def list_refreshes(
    season_id: UUID,
    dependencies: DataApi,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> RefreshRunPageResponse:
    return RefreshRunPageResponse(
        page=dependencies.refreshes.list_refreshes(
            RefreshRunQuery(
                competition_season_id=season_id,
                limit=limit,
                offset=offset,
            )
        )
    )


@router.get(
    "/refreshes/{refresh_id}",
    response_model=RefreshRunResponse,
)
def get_refresh(
    season_id: UUID,
    refresh_id: UUID,
    dependencies: DataApi,
) -> RefreshRunResponse:
    return RefreshRunResponse(
        refresh=dependencies.refreshes.get_refresh_for_season(
            season_id,
            refresh_id,
        )
    )


@router.get("/overview", response_model=LeagueSeasonOverviewResponse)
def get_league_season_overview(
    season_id: UUID,
    dependencies: DataApi,
) -> LeagueSeasonOverviewResponse:
    return LeagueSeasonOverviewResponse(
        overview=dependencies.league_seasons.get_season_overview(season_id)
    )


@router.get(
    "/snapshot-readiness",
    response_model=SnapshotReadinessResponse,
)
def inspect_snapshot_readiness(
    season_id: UUID,
    dependencies: DataApi,
    through_week: SnapshotWeek,
    mode: SnapshotPreparationMode,
) -> SnapshotReadinessResponse:
    checked_at = datetime.now(UTC)
    request = _snapshot_preparation_request(
        season_id=season_id,
        through_week=through_week,
        mode=mode,
        requested_at=checked_at,
    )
    return SnapshotReadinessResponse.from_service(
        checked_at=checked_at,
        mode=mode,
        through_week=through_week,
        readiness=dependencies.readiness.inspect(request),
    )


@router.post(
    "/snapshot-preparations",
    response_model=SnapshotPreparationResponse,
)
def prepare_snapshot(
    season_id: UUID,
    dependencies: DataApi,
    body: SnapshotPreparationBody,
) -> SnapshotPreparationResponse:
    requested_at = datetime.now(UTC)
    prepared = dependencies.preparation.get_or_create(
        _snapshot_preparation_request(
            season_id=season_id,
            through_week=body.through_week,
            mode=body.mode,
            requested_at=requested_at,
        )
    )
    return SnapshotPreparationResponse.from_resource(prepared)


@router.get("/snapshots", response_model=DataSnapshotPageResponse)
def list_snapshots(
    season_id: UUID,
    dependencies: DataApi,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> DataSnapshotPageResponse:
    page = dependencies.snapshots.list_snapshots(
        DataSnapshotQuery(
            competition_season_id=season_id,
            limit=limit,
            offset=offset,
        )
    )
    return DataSnapshotPageResponse(
        page=DataSnapshotSummaryPage(
            items=tuple(
                DataSnapshotSummary.from_resource(snapshot)
                for snapshot in page.items
            ),
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        )
    )


def _snapshot_preparation_request(
    *,
    season_id: UUID,
    through_week: int,
    mode: SnapshotPreparationMode,
    requested_at: datetime,
) -> PrepareSnapshotRequest:
    return PrepareSnapshotRequest(
        snapshot=SnapshotRequest(
            competition_season_id=season_id,
            through_week=through_week,
            as_of_date=requested_at.date(),
        ),
        mode=mode,
        requested_at=requested_at,
    )


__all__ = ["router"]
