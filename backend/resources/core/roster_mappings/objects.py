"""Caller-facing contracts for durable franchise and season-roster identity."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from backend.resources._contracts import ContractModel, NonBlankStr


class FranchiseIdentity(ContractModel):
    id: UUID
    competition_id: UUID
    display_name: str
    archived_at: AwareDatetime | None


class SeasonRosterIdentity(ContractModel):
    id: UUID
    competition_season_id: UUID
    franchise_id: UUID
    sleeper_roster_id: str


class RosterIdentityCatalog(ContractModel):
    competition_id: UUID
    competition_season_id: UUID
    sequence_number: Annotated[int, Field(strict=True, ge=1)]
    competition_archived: bool
    franchises: tuple[FranchiseIdentity, ...]
    mappings: tuple[SeasonRosterIdentity, ...]


class CreateFranchiseTarget(ContractModel):
    kind: Literal["new"] = "new"
    display_name: NonBlankStr


class ExistingFranchiseTarget(ContractModel):
    kind: Literal["existing"] = "existing"
    franchise_id: UUID


MappingTarget = Annotated[
    CreateFranchiseTarget | ExistingFranchiseTarget,
    Field(discriminator="kind"),
]


class RosterMappingAssignment(ContractModel):
    sleeper_roster_id: NonBlankStr
    target: MappingTarget


class ApplyRosterMappings(ContractModel):
    competition_season_id: UUID
    assignments: tuple[RosterMappingAssignment, ...]


__all__ = [
    "ApplyRosterMappings",
    "CreateFranchiseTarget",
    "ExistingFranchiseTarget",
    "FranchiseIdentity",
    "MappingTarget",
    "RosterIdentityCatalog",
    "RosterMappingAssignment",
    "SeasonRosterIdentity",
]
