"""Stable HTTP translation for competition resource failures."""

from typing import Literal

from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.resources.core import (
    CompetitionArchivedConflict,
    CompetitionConcurrencyConflict,
    CompetitionSeasonYearExists,
    CoreResourceError,
    CoreResourceNotFound,
    SleeperLeagueIdExists,
)


CoreErrorCode = Literal[
    "competition_not_found",
    "competition_season_not_found",
    "competition_archived",
    "competition_season_year_exists",
    "sleeper_league_id_exists",
    "competition_concurrency_conflict",
]


class CoreErrorDetail(BaseModel):
    code: CoreErrorCode
    summary: str
    field_errors: dict[str, list[str]] | None = None
    correlation_id: str | None = None


class CoreErrorResponse(BaseModel):
    error: CoreErrorDetail


async def core_resource_error_handler(
    request: Request,
    error: Exception,
) -> JSONResponse:
    if not isinstance(error, CoreResourceError):
        raise TypeError("core error handler received a non-core exception")
    status_code, code, summary, field_errors = _http_error(error)
    correlation_id = request.headers.get("X-Correlation-ID")
    payload = CoreErrorResponse(
        error=CoreErrorDetail(
            code=code,
            summary=summary,
            field_errors=field_errors,
            correlation_id=correlation_id,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(payload, exclude_none=True),
    )


def _http_error(
    error: CoreResourceError,
) -> tuple[int, CoreErrorCode, str, dict[str, list[str]] | None]:
    if isinstance(error, CoreResourceNotFound):
        if error.resource_kind == "competition":
            return (
                status.HTTP_404_NOT_FOUND,
                "competition_not_found",
                "competition was not found",
                None,
            )
        return (
            status.HTTP_404_NOT_FOUND,
            "competition_season_not_found",
            "competition season was not found",
            None,
        )
    if isinstance(error, CompetitionArchivedConflict):
        return (
            status.HTTP_409_CONFLICT,
            "competition_archived",
            "archived competitions cannot be changed",
            None,
        )
    if isinstance(error, CompetitionSeasonYearExists):
        return (
            status.HTTP_409_CONFLICT,
            "competition_season_year_exists",
            "that season year is already attached to this competition",
            {"season_year": ["Already attached to this competition."]},
        )
    if isinstance(error, SleeperLeagueIdExists):
        return (
            status.HTTP_409_CONFLICT,
            "sleeper_league_id_exists",
            "that Sleeper league ID is already attached to a season",
            {"sleeper_league_id": ["Already attached to another season."]},
        )
    if isinstance(error, CompetitionConcurrencyConflict):
        return (
            status.HTTP_409_CONFLICT,
            "competition_concurrency_conflict",
            "competition state changed concurrently; retry the request",
            None,
        )
    raise TypeError(f"unsupported core application error {type(error).__name__}")


__all__ = [
    "CoreErrorResponse",
    "core_resource_error_handler",
]
