"""Immutable snapshot lifecycle and membership resource contracts."""

from __future__ import annotations

from datetime import date
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


class SnapshotRequestMembership(ContractModel):
    request_id: UUID
    endpoint_kind: EndpointKind
    scope_key: ScopeKey
    response_sha256: Sha256
    selection_role: SnapshotSelectionRole


class SealSnapshot(ContractModel):
    requests: tuple[SnapshotRequestMembership, ...]
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
        return self


class DataSnapshot(ContractModel):
    id: UUID
    competition_id: UUID
    primary_competition_season_id: UUID
    build_key: Sha256
    through_week: int = Field(strict=True, ge=1, le=18)
    as_of_date: date
    status: SnapshotStatus
    snapshot_projection_version: str
    code_version: str
    completeness_warnings: tuple[CompletenessWarning, ...]
    failure: SnapshotFailure | None
    artifact: StoredLocalArtifact | None
    created_at: AwareDatetime
    completed_at: AwareDatetime | None


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
