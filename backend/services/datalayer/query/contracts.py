"""Immutable value contracts owned by the frozen query layer."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints


class QueryValue(BaseModel):
    """Dependency-free base for values returned by the frozen query runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


NonBlankStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


def _optional_display_name(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


DisplayName = Annotated[str | None, BeforeValidator(_optional_display_name)]


class SnapshotSeason(QueryValue):
    """One validated season available inside an immutable snapshot."""

    competition_id: UUID
    competition_season_id: UUID
    sleeper_league_id: NonBlankStr
    season_year: int = Field(strict=True, ge=1900, le=9999)
    sequence_number: int = Field(strict=True, ge=1)
    role: Literal["primary", "history"]
    through_week: int = Field(strict=True, ge=1, le=18)


__all__ = [
    "DisplayName",
    "NonBlankStr",
    "QueryValue",
    "SnapshotSeason",
]
