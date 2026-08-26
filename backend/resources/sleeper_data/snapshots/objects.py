"""Immutable snapshot lifecycle and membership resource contracts."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from backend.resources._contracts import ContractModel
from backend.services.datalayer.contracts import (
    CompletenessWarning,
    SnapshotSelectionRole,
    SnapshotStatus,
)
from backend.services.datalayer.local_files import StoredLocalArtifact
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


SafeCode = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    ),
]
SafeSummary = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
PageLimit = Annotated[int, Field(strict=True, ge=1, le=200)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]


class SnapshotFailure(ContractModel):
    code: SafeCode
    summary: SafeSummary


class ArtifactFailure(ContractModel):
    code: SafeCode
    summary: SafeSummary


class BeginSnapshotBuild(ContractModel):
    competition_season_id: UUID
    through_week: int = Field(strict=True, ge=1, le=18)
    as_of_date: date
    build_key: Sha256
    snapshot_projection_version: str = Field(min_length=1)
    code_version: str = Field(min_length=1)
    input_revision: Sha256 | None = None


class DataSnapshotQuery(ContractModel):
    competition_season_id: UUID
    limit: PageLimit = 50
    offset: NonNegativeInt = 0


class SnapshotRequestMembership(ContractModel):
    request_id: UUID
    endpoint_kind: EndpointKind
    scope_key: ScopeKey
    response_sha256: Sha256
    selection_role: SnapshotSelectionRole


class SnapshotSeasonRole(StrEnum):
    PRIMARY = "primary"
    HISTORY = "history"


class SealSnapshotSeason(ContractModel):
    competition_season_id: UUID
    role: SnapshotSeasonRole
    through_week: int = Field(strict=True, ge=1, le=18)


class SnapshotSeasonMembership(ContractModel):
    competition_id: UUID
    competition_season_id: UUID
    sleeper_league_id: str
    season_year: int = Field(strict=True, ge=1900, le=9999)
    sequence_number: int = Field(strict=True, ge=1)
    role: SnapshotSeasonRole
    through_week: int = Field(strict=True, ge=1, le=18)


class SealSnapshot(ContractModel):
    requests: tuple[SnapshotRequestMembership, ...]
    seasons: tuple[SealSnapshotSeason, ...] = ()
    artifact: StoredLocalArtifact
    completeness_warnings: tuple[CompletenessWarning, ...] = ()

    @model_validator(mode="after")
    def validate_requests(self) -> "SealSnapshot":
        if not self.requests:
            raise ValueError("a ready snapshot requires request membership")
        request_ids = [request.request_id for request in self.requests]
        scopes = [request.scope_key for request in self.requests]
        if len(request_ids) != len(set(request_ids)):
            raise ValueError("snapshot request IDs must be unique")
        if len(scopes) != len(set(scopes)):
            raise ValueError("snapshot request scopes must be unique")
        if not self.artifact.storage_key.startswith("snapshots/"):
            raise ValueError("snapshot seal requires a snapshot artifact")
        season_ids = [season.competition_season_id for season in self.seasons]
        if len(season_ids) != len(set(season_ids)):
            raise ValueError("snapshot season memberships must be unique")
        primary_count = sum(
            season.role is SnapshotSeasonRole.PRIMARY for season in self.seasons
        )
        if self.seasons and primary_count != 1:
            raise ValueError("explicit snapshot seasons require exactly one primary")
        return self


class DataSnapshot(ContractModel):
    id: UUID
    competition_id: UUID
    primary_competition_season_id: UUID
    build_key: Sha256
    input_revision: Sha256 | None = None
    through_week: int = Field(strict=True, ge=1, le=18)
    as_of_date: date
    status: SnapshotStatus
    snapshot_projection_version: str
    code_version: str
    completeness_warnings: tuple[CompletenessWarning, ...]
    failure: SnapshotFailure | None
    artifact: StoredLocalArtifact | None
    included_seasons: tuple[SnapshotSeasonMembership, ...] = ()
    created_at: AwareDatetime
    completed_at: AwareDatetime | None


class DataSnapshotPage(ContractModel):
    items: tuple[DataSnapshot, ...]
    total: NonNegativeInt
    limit: PageLimit
    offset: NonNegativeInt


class ClaimedSnapshotBuild(ContractModel):
    kind: Literal["claimed"] = "claimed"
    snapshot: DataSnapshot


class ExistingBuildingSnapshot(ContractModel):
    kind: Literal["building"] = "building"
    snapshot: DataSnapshot


class ExistingReadySnapshot(ContractModel):
    kind: Literal["ready"] = "ready"
    snapshot: DataSnapshot


SnapshotBuildState: TypeAlias = Annotated[
    ClaimedSnapshotBuild | ExistingBuildingSnapshot | ExistingReadySnapshot,
    Field(discriminator="kind"),
]
