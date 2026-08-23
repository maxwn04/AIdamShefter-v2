"""Strict transport models for refresh and data-audit routes."""

from datetime import date
from typing import Annotated, ClassVar
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from backend.resources.sleeper_data import (
    DataSnapshot,
    LeagueSeasonOverview,
    RefreshRun,
    RefreshRunPage,
)
from backend.resources.sleeper_data.snapshots import SnapshotFailure
from backend.services.datalayer import CompletenessWarning, ScopeRefreshResult
from backend.services.datalayer.contracts import SnapshotStatus


class DataApiModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class ManualRefreshBody(DataApiModel):
    through_week: Annotated[int, Field(strict=True, ge=1, le=18)] | None = None

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{}, {"through_week": 8}]},
    )


class ManualRefreshResponse(DataApiModel):
    refresh: RefreshRun
    effective_through_week: int | None
    scope_results: tuple[ScopeRefreshResult, ...]


class RefreshRunResponse(DataApiModel):
    refresh: RefreshRun


class RefreshRunPageResponse(DataApiModel):
    page: RefreshRunPage


class LeagueSeasonOverviewResponse(DataApiModel):
    overview: LeagueSeasonOverview


class SnapshotArtifactSummary(DataApiModel):
    sha256: str
    byte_length: int


class DataSnapshotSummary(DataApiModel):
    id: UUID
    competition_id: UUID
    primary_competition_season_id: UUID
    build_key: str
    through_week: int
    as_of_date: date
    status: SnapshotStatus
    snapshot_projection_version: str
    code_version: str
    completeness_warnings: tuple[CompletenessWarning, ...]
    failure: SnapshotFailure | None
    artifact: SnapshotArtifactSummary | None
    created_at: AwareDatetime
    completed_at: AwareDatetime | None

    @classmethod
    def from_resource(cls, snapshot: DataSnapshot) -> "DataSnapshotSummary":
        artifact = snapshot.artifact
        return cls(
            id=snapshot.id,
            competition_id=snapshot.competition_id,
            primary_competition_season_id=snapshot.primary_competition_season_id,
            build_key=snapshot.build_key,
            through_week=snapshot.through_week,
            as_of_date=snapshot.as_of_date,
            status=snapshot.status,
            snapshot_projection_version=snapshot.snapshot_projection_version,
            code_version=snapshot.code_version,
            completeness_warnings=snapshot.completeness_warnings,
            failure=snapshot.failure,
            artifact=(
                None
                if artifact is None
                else SnapshotArtifactSummary(
                    sha256=artifact.sha256,
                    byte_length=artifact.byte_length,
                )
            ),
            created_at=snapshot.created_at,
            completed_at=snapshot.completed_at,
        )


class DataSnapshotSummaryPage(DataApiModel):
    items: tuple[DataSnapshotSummary, ...]
    total: int
    limit: int
    offset: int


class DataSnapshotPageResponse(DataApiModel):
    page: DataSnapshotSummaryPage


__all__ = [
    "DataSnapshotPageResponse",
    "DataSnapshotSummary",
    "DataSnapshotSummaryPage",
    "LeagueSeasonOverviewResponse",
    "ManualRefreshBody",
    "ManualRefreshResponse",
    "RefreshRunPageResponse",
    "RefreshRunResponse",
]
