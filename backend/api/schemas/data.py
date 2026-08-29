"""Strict transport models for refresh and data-audit routes."""

from datetime import date
from typing import Annotated, ClassVar, Literal, TypeAlias
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from backend.resources.sleeper_data import (
    DataSnapshot,
    LeagueSeasonOverview,
    RefreshRun,
    RefreshRunPage,
)
from backend.resources.sleeper_data.snapshots import SnapshotFailure
from backend.services.datalayer import (
    CompletenessWarning,
    PreparedSnapshot,
    ReadyDataSnapshot,
    ReadySnapshotReadiness,
    RefreshRequiredSnapshotReadiness,
    RosterMappingRequiredSnapshotReadiness,
    ScopeRefreshResult,
    SnapshotPreparationMode,
    SnapshotReadiness,
    SnapshotReadinessSeason,
)
from backend.services.datalayer.contracts import SnapshotStatus
from backend.services.datalayer.refresh_coordination import RefreshReceipt


class DataApiModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class ManualRefreshBody(DataApiModel):
    through_week: Annotated[int, Field(strict=True, ge=1, le=18)] | None = None

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{}, {"through_week": 8}]},
    )


class SnapshotPreparationBody(DataApiModel):
    through_week: Annotated[int, Field(strict=True, ge=1, le=18)]
    mode: SnapshotPreparationMode


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


class SnapshotSeasonSummary(DataApiModel):
    competition_season_id: UUID
    sleeper_league_id: str
    season_year: int
    sequence_number: int
    role: Literal["primary", "history"]
    through_week: int


class ReadySnapshotReadinessState(DataApiModel):
    kind: Literal["ready"] = "ready"
    input_revision: str
    included_seasons: tuple[SnapshotSeasonSummary, ...]


class RefreshRequiredSnapshotReadinessState(DataApiModel):
    kind: Literal["refresh_required"] = "refresh_required"
    season: SnapshotSeasonSummary
    reason: Literal["missing", "stale"]
    missing_scopes: tuple[str, ...]


class RosterMappingRequiredSnapshotReadinessState(DataApiModel):
    kind: Literal["roster_mapping_required"] = "roster_mapping_required"
    season: SnapshotSeasonSummary
    sleeper_roster_ids: tuple[str, ...]


SnapshotReadinessState: TypeAlias = Annotated[
    ReadySnapshotReadinessState
    | RefreshRequiredSnapshotReadinessState
    | RosterMappingRequiredSnapshotReadinessState,
    Field(discriminator="kind"),
]


class SnapshotReadinessResponse(DataApiModel):
    checked_at: AwareDatetime
    mode: SnapshotPreparationMode
    through_week: int
    state: SnapshotReadinessState

    @classmethod
    def from_service(
        cls,
        *,
        checked_at: AwareDatetime,
        mode: SnapshotPreparationMode,
        through_week: int,
        readiness: SnapshotReadiness,
    ) -> "SnapshotReadinessResponse":
        if isinstance(readiness, ReadySnapshotReadiness):
            state: SnapshotReadinessState = ReadySnapshotReadinessState(
                input_revision=readiness.input_revision,
                included_seasons=tuple(
                    _season_summary(season)
                    for season in readiness.included_seasons
                ),
            )
        elif isinstance(readiness, RefreshRequiredSnapshotReadiness):
            state = RefreshRequiredSnapshotReadinessState(
                season=_season_summary(readiness.season),
                reason=readiness.reason.value,
                missing_scopes=tuple(
                    scope.value for scope in readiness.missing_scopes
                ),
            )
        elif isinstance(readiness, RosterMappingRequiredSnapshotReadiness):
            state = RosterMappingRequiredSnapshotReadinessState(
                season=_season_summary(readiness.season),
                sleeper_roster_ids=readiness.sleeper_roster_ids,
            )
        else:
            raise AssertionError(
                f"unsupported snapshot readiness: {type(readiness)!r}"
            )
        return cls(
            checked_at=checked_at,
            mode=mode,
            through_week=through_week,
            state=state,
        )


class SnapshotRefreshReceiptSummary(DataApiModel):
    claim_id: UUID
    refresh_run_id: UUID
    competition_season_id: UUID
    through_week: int
    status: Literal["succeeded", "partial", "failed", "cancelled"]
    disposition: Literal["claimed", "joined"]

    @classmethod
    def from_service(
        cls,
        receipt: RefreshReceipt,
    ) -> "SnapshotRefreshReceiptSummary":
        return cls(
            claim_id=receipt.claim_id,
            refresh_run_id=receipt.refresh_run_id,
            competition_season_id=receipt.competition_season_id,
            through_week=receipt.through_week,
            status=receipt.status.value,
            disposition=receipt.disposition.value,
        )


class PreparedSnapshotSummary(DataApiModel):
    id: UUID
    competition_id: UUID
    primary_competition_season_id: UUID
    through_week: int
    as_of_date: date
    build_key: str
    snapshot_projection_version: str
    artifact: SnapshotArtifactSummary
    completeness_warnings: tuple[CompletenessWarning, ...]
    input_revision: str | None
    included_seasons: tuple[SnapshotSeasonSummary, ...]

    @classmethod
    def from_resource(
        cls,
        snapshot: ReadyDataSnapshot,
    ) -> "PreparedSnapshotSummary":
        return cls(
            id=snapshot.id,
            competition_id=snapshot.competition_id,
            primary_competition_season_id=(
                snapshot.primary_competition_season_id
            ),
            through_week=snapshot.through_week,
            as_of_date=snapshot.as_of_date,
            build_key=snapshot.build_key,
            snapshot_projection_version=snapshot.snapshot_projection_version,
            artifact=SnapshotArtifactSummary(
                sha256=snapshot.artifact.sha256,
                byte_length=snapshot.artifact.byte_length,
            ),
            completeness_warnings=snapshot.completeness_warnings,
            input_revision=snapshot.input_revision,
            included_seasons=tuple(
                SnapshotSeasonSummary(
                    competition_season_id=season.competition_season_id,
                    sleeper_league_id=season.sleeper_league_id,
                    season_year=season.season_year,
                    sequence_number=season.sequence_number,
                    role=season.role,
                    through_week=season.through_week,
                )
                for season in snapshot.included_seasons
            ),
        )


class SnapshotPreparationResponse(DataApiModel):
    snapshot: PreparedSnapshotSummary
    refresh_receipts: tuple[SnapshotRefreshReceiptSummary, ...]

    @classmethod
    def from_resource(
        cls,
        prepared: PreparedSnapshot,
    ) -> "SnapshotPreparationResponse":
        return cls(
            snapshot=PreparedSnapshotSummary.from_resource(prepared.snapshot),
            refresh_receipts=tuple(
                SnapshotRefreshReceiptSummary.from_service(receipt)
                for receipt in prepared.refresh_receipts
            ),
        )


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
    input_revision: str | None
    included_seasons: tuple[SnapshotSeasonSummary, ...]
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
            input_revision=snapshot.input_revision,
            included_seasons=tuple(
                SnapshotSeasonSummary(
                    competition_season_id=season.competition_season_id,
                    sleeper_league_id=season.sleeper_league_id,
                    season_year=season.season_year,
                    sequence_number=season.sequence_number,
                    role=season.role.value,
                    through_week=season.through_week,
                )
                for season in snapshot.included_seasons
            ),
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


def _season_summary(season: SnapshotReadinessSeason) -> SnapshotSeasonSummary:
    return SnapshotSeasonSummary(
        competition_season_id=season.competition_season_id,
        sleeper_league_id=season.sleeper_league_id,
        season_year=season.season_year,
        sequence_number=season.sequence_number,
        role=season.role.value,
        through_week=season.through_week,
    )


__all__ = [
    "DataSnapshotPageResponse",
    "DataSnapshotSummary",
    "DataSnapshotSummaryPage",
    "LeagueSeasonOverviewResponse",
    "ManualRefreshBody",
    "ManualRefreshResponse",
    "PreparedSnapshotSummary",
    "RefreshRunPageResponse",
    "RefreshRunResponse",
    "SnapshotPreparationBody",
    "SnapshotPreparationResponse",
    "SnapshotReadinessResponse",
    "SnapshotSeasonSummary",
]
