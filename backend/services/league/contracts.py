"""HTTP-independent contracts for season roster identity onboarding."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from backend.resources._contracts import ContractModel
from backend.resources.core import FranchiseIdentity, RosterMappingAssignment


class RosterManagerEvidence(ContractModel):
    sleeper_user_id: str
    display_name: str
    team_name: str | None = None
    role: Literal["owner", "co_owner"]


class ObservedRosterMapping(ContractModel):
    sleeper_roster_id: str
    suggested_display_name: str
    managers: tuple[RosterManagerEvidence, ...]
    franchise_id: UUID | None = None
    franchise_name: str | None = None


class RosterMappingView(ContractModel):
    status: Literal["awaiting_source", "needs_mapping", "ready"]
    source_api_request_id: UUID | None = None
    source_observed_at: AwareDatetime | None = None
    roster_count: int = Field(strict=True, ge=0)
    mapped_count: int = Field(strict=True, ge=0)
    rosters: tuple[ObservedRosterMapping, ...]
    franchise_options: tuple[FranchiseIdentity, ...]


class ReconcileRosterMappings(ContractModel):
    source_api_request_id: UUID
    assignments: tuple[RosterMappingAssignment, ...]


class RosterMappingResult(ContractModel):
    mapping: RosterMappingView
    replay_status: Literal["applied", "deferred"]


__all__ = [
    "ObservedRosterMapping",
    "ReconcileRosterMappings",
    "RosterManagerEvidence",
    "RosterMappingResult",
    "RosterMappingView",
]
