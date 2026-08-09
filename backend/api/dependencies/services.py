"""Access to process-scoped services and infrastructure."""

from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import Depends, Request

from backend.api.dependencies.context import get_competition_manager_context
from backend.composition import (
    ApiRuntime,
    ApiRuntimeDependencies,
    open_datalayer_refresh_service,
)
from backend.resources.context import ManagerContext
from backend.resources.sleeper_data.manager import SleeperDataManager
from backend.services.datalayer.refresh_service import DatalayerRefreshService


def get_api_runtime(request: Request) -> ApiRuntimeDependencies:
    """Return dependencies built by the application lifespan."""

    return cast(ApiRuntimeDependencies, request.app.state.runtime)


def get_datalayer_refresh_service(
    runtime: Annotated[ApiRuntimeDependencies, Depends(get_api_runtime)],
    context: Annotated[ManagerContext, Depends(get_competition_manager_context)],
) -> Iterator[DatalayerRefreshService]:
    """Yield a concrete refresh workflow scoped to the path competition."""

    with open_datalayer_refresh_service(cast(ApiRuntime, runtime), context) as service:
        yield service


def get_sleeper_data_manager(
    runtime: Annotated[ApiRuntimeDependencies, Depends(get_api_runtime)],
    context: Annotated[ManagerContext, Depends(get_competition_manager_context)],
) -> SleeperDataManager:
    """Construct one manager whose reads are bound to the path competition."""

    return SleeperDataManager(cast(ApiRuntime, runtime).session_factory, context)
