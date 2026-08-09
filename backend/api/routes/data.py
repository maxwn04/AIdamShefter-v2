"""Sleeper-data HTTP routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.api.dependencies.services import (
    get_datalayer_refresh_service,
    get_sleeper_data_manager,
)
from backend.api.schemas.data import (
    DataRefreshAuditResponse,
    DataRefreshCreateRequest,
    DataRefreshResponse,
    DataRequestAuditPageResponse,
)
from backend.resources.errors import (
    InvalidResourceCommand,
    ResourceConflict,
    ResourceNotFound,
)
from backend.services.datalayer.contracts import RefreshRequest, RefreshTrigger
from backend.services.datalayer.errors import InternalDatalayerFailure
from backend.services.datalayer.refresh_service import DatalayerRefreshService
from backend.resources.sleeper_data.manager import SleeperDataManager

router = APIRouter(tags=["data"])


@router.post(
    "/competitions/{competition_id}/seasons/{season_id}/data-refreshes",
    response_model=DataRefreshResponse,
)
def create_data_refresh(
    season_id: UUID,
    body: DataRefreshCreateRequest,
    service: Annotated[
        DatalayerRefreshService,
        Depends(get_datalayer_refresh_service),
    ],
) -> DataRefreshResponse:
    """Run the standard manual refresh synchronously and return its audit."""

    try:
        outcome = service.refresh(
            RefreshRequest(
                competition_season_id=season_id,
                through_week=body.through_week,
                trigger=RefreshTrigger.MANUAL,
            )
        )
    except ResourceNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="data resource not found",
        ) from error
    except ResourceConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="data refresh conflicts with current state",
        ) from error
    except InvalidResourceCommand as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid data refresh request",
        ) from error
    except InternalDatalayerFailure as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "internal_datalayer_failure",
                "correlation_id": error.correlation_id,
            },
        ) from error
    return DataRefreshResponse.from_outcome(outcome)


@router.get(
    "/competitions/{competition_id}/data-refreshes/{refresh_id}",
    response_model=DataRefreshAuditResponse,
)
def get_data_refresh(
    refresh_id: UUID,
    manager: Annotated[
        SleeperDataManager,
        Depends(get_sleeper_data_manager),
    ],
) -> DataRefreshAuditResponse:
    """Return a competition-scoped refresh audit."""

    try:
        refresh = manager.get_refresh(refresh_id)
    except ResourceNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="data resource not found",
        ) from error
    return DataRefreshAuditResponse.from_resource(refresh)


@router.get(
    "/competitions/{competition_id}/data-refreshes/{refresh_id}/requests",
    response_model=DataRequestAuditPageResponse,
)
def list_data_refresh_requests(
    refresh_id: UUID,
    manager: Annotated[
        SleeperDataManager,
        Depends(get_sleeper_data_manager),
    ],
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DataRequestAuditPageResponse:
    """Return sanitized request attempts for one competition-scoped refresh."""

    try:
        page = manager.list_refresh_requests(
            refresh_id,
            limit=limit,
            offset=offset,
        )
    except ResourceNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="data resource not found",
        ) from error
    return DataRequestAuditPageResponse.from_resource(page)
