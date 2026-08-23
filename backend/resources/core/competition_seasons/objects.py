"""Immutable commands and views for competition season identities."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field

from backend.resources._contracts import ContractModel, NonBlankStr


PageLimit = Annotated[int, Field(strict=True, ge=1, le=200)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
SeasonYear = Annotated[int, Field(strict=True, ge=1900, le=9999)]
SequenceNumber = Annotated[int, Field(strict=True, ge=1)]


class CreateCompetitionSeason(ContractModel):
    season_year: SeasonYear
    sleeper_league_id: NonBlankStr


class CompetitionSeasonQuery(ContractModel):
    limit: PageLimit = 50
    offset: NonNegativeInt = 0


class CompetitionSeason(ContractModel):
    id: UUID
    competition_id: UUID
    season_year: SeasonYear
    sequence_number: SequenceNumber
    sleeper_league_id: str
    created_at: AwareDatetime


class CompetitionSeasonPage(ContractModel):
    items: tuple[CompetitionSeason, ...]
    total: NonNegativeInt
    limit: PageLimit
    offset: NonNegativeInt


__all__ = [
    "CompetitionSeason",
    "CompetitionSeasonPage",
    "CompetitionSeasonQuery",
    "CreateCompetitionSeason",
]
