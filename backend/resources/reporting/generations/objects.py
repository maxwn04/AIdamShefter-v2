"""Immutable commands and views for one durable generation resource."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import (
    AwareDatetime,
    Field,
    JsonValue,
    StringConstraints,
    model_validator,
)

from backend.resources._contracts import ContractModel, NonBlankStr


PositiveWeek = Annotated[int, Field(strict=True, ge=1, le=18)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, ge=1)]
PageLimit = Annotated[int, Field(strict=True, ge=1, le=200)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
FailureCategory = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    ),
]
FailureSummary = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


class GenerationKind(StrEnum):
    LIVE = "live"
    BACKTEST = "backtest"


class GenerationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CreateGeneration(ContractModel):
    generation_id: UUID
    competition_season_id: UUID
    kind: GenerationKind
    request_text: NonBlankStr
    week_start: PositiveWeek | None = None
    week_end: PositiveWeek | None = None
    requested_primary_model: NonBlankStr
    settings: dict[str, JsonValue]
    rerun_of_generation_id: UUID | None = None
    evaluation_workspace_id: UUID | None = None
    workspace_sequence_number: PositiveInt | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "CreateGeneration":
        if (self.week_start is None) != (self.week_end is None):
            raise ValueError("week_start and week_end must be provided together")
        if (
            self.week_start is not None
            and self.week_end is not None
            and self.week_start > self.week_end
        ):
            raise ValueError("week_start cannot be after week_end")
        if (self.evaluation_workspace_id is None) != (
            self.workspace_sequence_number is None
        ):
            raise ValueError(
                "evaluation workspace ID and sequence number must be provided together"
            )
        return self


class StartGeneration(ContractModel):
    generation_id: UUID
    data_snapshot_id: UUID
    input_memory_revision_id: UUID | None = None
    input_memory_artifact_version_id: UUID | None = None
    input_memory_artifact_generation_id: UUID | None = None
    knowledge_cutoff_at: AwareDatetime
    input_manifest: dict[str, JsonValue]
    manifest_schema_version: PositiveInt
    manifest_hash: Sha256
    initial_stage: NonBlankStr = "starting"

    @model_validator(mode="after")
    def validate_memory_input(self) -> "StartGeneration":
        artifact_shape = (
            self.input_memory_artifact_version_id is not None
            and self.input_memory_artifact_generation_id is not None
        )
        if (self.input_memory_artifact_version_id is None) != (
            self.input_memory_artifact_generation_id is None
        ):
            raise ValueError("workspace memory input requires both artifact IDs")
        if (self.input_memory_revision_id is not None) == artifact_shape:
            raise ValueError("start requires exactly one resolved memory input")
        if not self.input_manifest:
            raise ValueError("start requires a non-empty input manifest")
        return self


class UpdateGenerationProgress(ContractModel):
    generation_id: UUID
    current_turn: NonNegativeInt
    current_stage: NonBlankStr


class FailGeneration(ContractModel):
    generation_id: UUID
    category: FailureCategory
    summary: FailureSummary


class CancelGeneration(ContractModel):
    generation_id: UUID
    summary: FailureSummary | None = None


class GenerationQuery(ContractModel):
    competition_season_id: UUID | None = None
    kind: GenerationKind | None = None
    status: GenerationStatus | None = None
    rerun_of_generation_id: UUID | None = None
    evaluation_workspace_id: UUID | None = None
    limit: PageLimit = 50
    offset: NonNegativeInt = 0


class Generation(ContractModel):
    id: UUID
    competition_id: UUID
    competition_season_id: UUID
    data_snapshot_id: UUID | None
    input_memory_revision_id: UUID | None
    input_memory_artifact_version_id: UUID | None
    input_memory_artifact_generation_id: UUID | None
    evaluation_workspace_id: UUID | None
    workspace_sequence_number: int | None
    rerun_of_generation_id: UUID | None
    kind: GenerationKind
    status: GenerationStatus
    request_text: str
    week_start: int | None
    week_end: int | None
    domain_cutoff_week: int | None
    domain_cutoff_at: AwareDatetime | None
    knowledge_cutoff_at: AwareDatetime | None
    requested_primary_model: str
    settings: dict[str, JsonValue]
    input_manifest: dict[str, JsonValue] | None
    manifest_schema_version: int | None
    manifest_hash: str | None
    current_turn: int
    current_stage: str | None
    progress_updated_at: AwareDatetime | None
    failure_category: str | None
    failure_summary: str | None
    created_at: AwareDatetime
    started_at: AwareDatetime | None
    completed_at: AwareDatetime | None


class GenerationDetail(Generation):
    """Complete generation row without child-resource payloads."""


class GenerationSummary(ContractModel):
    id: UUID
    competition_id: UUID
    competition_season_id: UUID
    evaluation_workspace_id: UUID | None
    workspace_sequence_number: int | None
    rerun_of_generation_id: UUID | None
    kind: GenerationKind
    status: GenerationStatus
    request_text: str
    week_start: int | None
    week_end: int | None
    requested_primary_model: str
    current_turn: int
    current_stage: str | None
    progress_updated_at: AwareDatetime | None
    failure_category: str | None
    failure_summary: str | None
    created_at: AwareDatetime
    started_at: AwareDatetime | None
    completed_at: AwareDatetime | None


class GenerationPage(ContractModel):
    items: tuple[GenerationSummary, ...]
    total: NonNegativeInt
    limit: PageLimit
    offset: NonNegativeInt


__all__ = [
    "CancelGeneration",
    "CreateGeneration",
    "FailGeneration",
    "Generation",
    "GenerationDetail",
    "GenerationKind",
    "GenerationPage",
    "GenerationQuery",
    "GenerationStatus",
    "GenerationSummary",
    "StartGeneration",
    "UpdateGenerationProgress",
]
