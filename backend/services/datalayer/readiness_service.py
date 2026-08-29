"""Safe, network-free snapshot readiness inspection."""

from __future__ import annotations

from typing import Annotated, Literal, Protocol, TypeAlias
from uuid import UUID

from pydantic import Field

from backend.resources._contracts import ContractModel
from backend.resources.sleeper_data.league_seasons import SnapshotSeasonIdentity
from backend.resources.sleeper_data.refreshes import RefreshNeedReason
from backend.resources.sleeper_data.snapshots import SnapshotSeasonRole
from backend.services.datalayer.snapshot_inputs import (
    MapSeasonRosters,
    PrepareSnapshotRequest,
    RefreshSeason,
    ResolvedSnapshotInputs,
    ResolutionState,
)
from backend.services.datalayer.sleeper.scope import ScopeKey


class SnapshotReadinessSeason(ContractModel):
    competition_season_id: UUID
    sleeper_league_id: str
    season_year: int = Field(strict=True, ge=1900, le=9999)
    sequence_number: int = Field(strict=True, ge=1)
    role: SnapshotSeasonRole
    through_week: int = Field(strict=True, ge=1, le=18)


class ReadySnapshotReadiness(ContractModel):
    kind: Literal["ready"] = "ready"
    input_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    included_seasons: tuple[SnapshotReadinessSeason, ...]


class RefreshRequiredSnapshotReadiness(ContractModel):
    kind: Literal["refresh_required"] = "refresh_required"
    season: SnapshotReadinessSeason
    reason: RefreshNeedReason
    missing_scopes: tuple[ScopeKey, ...] = ()


class RosterMappingRequiredSnapshotReadiness(ContractModel):
    kind: Literal["roster_mapping_required"] = "roster_mapping_required"
    season: SnapshotReadinessSeason
    sleeper_roster_ids: tuple[str, ...]


SnapshotReadiness: TypeAlias = Annotated[
    ReadySnapshotReadiness
    | RefreshRequiredSnapshotReadiness
    | RosterMappingRequiredSnapshotReadiness,
    Field(discriminator="kind"),
]


class SnapshotReadinessResolver(Protocol):
    def resolve(self, request: PrepareSnapshotRequest) -> ResolutionState: ...


class DatalayerSnapshotReadinessService:
    """Project the resolver's closed state into a safe inspection result."""

    def __init__(self, resolver: SnapshotReadinessResolver) -> None:
        self._resolver = resolver

    def inspect(self, request: PrepareSnapshotRequest) -> SnapshotReadiness:
        state = self._resolver.resolve(request)
        if isinstance(state, ResolvedSnapshotInputs):
            return ReadySnapshotReadiness(
                input_revision=state.input_revision,
                included_seasons=tuple(
                    _season(
                        item.identity,
                        role=item.role,
                        through_week=item.through_week,
                    )
                    for item in state.seasons
                ),
            )
        if isinstance(state, RefreshSeason):
            return RefreshRequiredSnapshotReadiness(
                season=_season(
                    state.season,
                    role=_role(request, state.season),
                    through_week=state.through_week,
                ),
                reason=state.reason,
                missing_scopes=state.missing_scopes,
            )
        if isinstance(state, MapSeasonRosters):
            return RosterMappingRequiredSnapshotReadiness(
                season=_season(
                    state.season,
                    role=_role(request, state.season),
                    through_week=(
                        request.snapshot.through_week
                        if state.season.competition_season_id
                        == request.snapshot.competition_season_id
                        else 18
                    ),
                ),
                sleeper_roster_ids=state.roster_ids,
            )
        raise AssertionError(f"unsupported readiness state: {type(state)!r}")


def _season(
    identity: SnapshotSeasonIdentity,
    *,
    role: SnapshotSeasonRole,
    through_week: int,
) -> SnapshotReadinessSeason:
    return SnapshotReadinessSeason(
        competition_season_id=identity.competition_season_id,
        sleeper_league_id=identity.sleeper_league_id,
        season_year=identity.season_year,
        sequence_number=identity.sequence_number,
        role=role,
        through_week=through_week,
    )


def _role(
    request: PrepareSnapshotRequest,
    identity: SnapshotSeasonIdentity,
) -> SnapshotSeasonRole:
    return (
        SnapshotSeasonRole.PRIMARY
        if identity.competition_season_id
        == request.snapshot.competition_season_id
        else SnapshotSeasonRole.HISTORY
    )


__all__ = [
    "DatalayerSnapshotReadinessService",
    "ReadySnapshotReadiness",
    "RefreshRequiredSnapshotReadiness",
    "RosterMappingRequiredSnapshotReadiness",
    "SnapshotReadiness",
    "SnapshotReadinessSeason",
]
