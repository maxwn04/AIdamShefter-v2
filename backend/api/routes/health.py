"""Process liveness and database readiness routes."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from backend.api.dependencies.services import get_api_runtime
from backend.composition import ApiRuntimeDependencies

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["alive", "ready"]


@router.get("/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    """Report process liveness without touching the database."""

    return HealthResponse(status="alive")


@router.get("/ready", response_model=HealthResponse)
def readiness(
    runtime: Annotated[ApiRuntimeDependencies, Depends(get_api_runtime)],
) -> HealthResponse:
    """Report readiness only when bounded database checks pass."""

    try:
        runtime.assert_ready()
    except (RuntimeError, SQLAlchemyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="service is not ready",
        ) from exc
    return HealthResponse(status="ready")
