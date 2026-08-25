"""Immutable commands and views for durable competition identities."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field

from backend.resources._contracts import ContractModel, NonBlankStr


PageLimit = Annotated[int, Field(strict=True, ge=1, le=200)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]


class CreateCompetition(ContractModel):
    display_name: NonBlankStr


class RenameCompetition(ContractModel):
    competition_id: UUID
    display_name: NonBlankStr


class ArchiveCompetition(ContractModel):
    competition_id: UUID


class CompetitionQuery(ContractModel):
    include_archived: bool = False
    limit: PageLimit = 50
    offset: NonNegativeInt = 0


class Competition(ContractModel):
    id: UUID
    display_name: str
    created_at: AwareDatetime
    updated_at: AwareDatetime
    archived_at: AwareDatetime | None


class CompetitionPage(ContractModel):
    items: tuple[Competition, ...]
    total: NonNegativeInt
    limit: PageLimit
    offset: NonNegativeInt


__all__ = [
    "ArchiveCompetition",
    "Competition",
    "CompetitionPage",
    "CompetitionQuery",
    "CreateCompetition",
    "RenameCompetition",
]
