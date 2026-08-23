"""Typed workflow values for generation submission and execution."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from backend.resources._contracts import ContractModel, NonBlankStr
from backend.resources.reporting.generations import (
    Generation,
    GenerationKind,
    GenerationStatus,
)
from backend.services.memory import MemoryMutationResult
from backend.services.reporter import ReporterOutput


PositiveWeek = Annotated[int, Field(strict=True, ge=1, le=18)]
PositiveInt = Annotated[int, Field(strict=True, ge=1)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
ControlLevel = Annotated[int, Field(strict=True, ge=0, le=3)]


class GenerationToneSettings(ContractModel):
    snark_level: ControlLevel = 1
    hype_level: ControlLevel = 1
    seriousness: ControlLevel = 1


class GenerationBiasSettings(ContractModel):
    favored_teams: tuple[NonBlankStr, ...] = ()
    disfavored_teams: tuple[NonBlankStr, ...] = ()
    intensity: ControlLevel = 1


class GenerationReportSettings(ContractModel):
    focus_hints: tuple[NonBlankStr, ...] = ()
    avoid_topics: tuple[NonBlankStr, ...] = ()
    focus_teams: tuple[NonBlankStr, ...] = ()
    voice: NonBlankStr = "sports columnist"
    tone: GenerationToneSettings = Field(default_factory=GenerationToneSettings)
    profanity_policy: Literal["none", "mild", "unrestricted"] = "none"
    bias: GenerationBiasSettings | None = None
    length_target: PositiveInt = 1000
    evidence_policy: Literal["strict", "standard", "relaxed"] = "standard"


class GenerationRetrySettings(ContractModel):
    max_retries: NonNegativeInt = 3
    base_delay_seconds: float = Field(default=1.0, gt=0)
    max_delay_seconds: float = Field(default=30.0, gt=0)

    @model_validator(mode="after")
    def validate_delays(self) -> "GenerationRetrySettings":
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max delay must be greater than or equal to base delay")
        return self


class GenerationModelSettings(ContractModel):
    fallback_models: tuple[NonBlankStr, ...] = ()
    retry: GenerationRetrySettings = Field(default_factory=GenerationRetrySettings)

    @model_validator(mode="after")
    def validate_fallbacks(self) -> "GenerationModelSettings":
        if len(self.fallback_models) != len(set(self.fallback_models)):
            raise ValueError("fallback models must be unique")
        return self


class GenerationRunnerSettings(ContractModel):
    max_turns: PositiveInt = 60
    procedure_history_mode: Literal["replace", "append"] = "replace"


class GenerationSettings(ContractModel):
    report: GenerationReportSettings = Field(default_factory=GenerationReportSettings)
    model: GenerationModelSettings = Field(default_factory=GenerationModelSettings)
    runner: GenerationRunnerSettings = Field(default_factory=GenerationRunnerSettings)


class GenerationRequest(ContractModel):
    generation_id: UUID
    competition_id: UUID
    competition_season_id: UUID
    kind: GenerationKind
    request_text: NonBlankStr
    week_start: PositiveWeek
    week_end: PositiveWeek
    requested_primary_model: NonBlankStr
    settings: GenerationSettings = Field(default_factory=GenerationSettings)
    rerun_of_generation_id: UUID | None = None

    @model_validator(mode="after")
    def validate_week_range(self) -> "GenerationRequest":
        if self.week_start > self.week_end:
            raise ValueError("week_start cannot be after week_end")
        chain = (
            self.requested_primary_model,
            *self.settings.model.fallback_models,
        )
        if len(chain) != len(set(chain)):
            raise ValueError("resolved model chain must not contain duplicates")
        return self


class GenerationExecutionResult(ContractModel):
    generation: Generation
    reporter_output: ReporterOutput | None = None
    memory_result: MemoryMutationResult | None = None

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> "GenerationExecutionResult":
        if self.generation.status is GenerationStatus.SUCCEEDED:
            if self.reporter_output is None:
                raise ValueError("successful execution requires reporter output")
            if self.generation.submitted_artifact_version_id is None:
                raise ValueError("successful execution requires a submitted version")
            return self
        if self.generation.status not in {
            GenerationStatus.FAILED,
            GenerationStatus.CANCELLED,
        }:
            raise ValueError("execution result requires a terminal generation")
        if self.reporter_output is not None or self.memory_result is not None:
            raise ValueError("unsuccessful execution cannot expose ephemeral output")
        return self


class RerunGenerationRequest(ContractModel):
    source_generation_id: UUID
    generation_id: UUID

    @model_validator(mode="after")
    def validate_distinct_ids(self) -> "RerunGenerationRequest":
        if self.source_generation_id == self.generation_id:
            raise ValueError("rerun generation ID must differ from its source")
        return self


class StaleGenerationPolicy(ContractModel):
    stale_before: AwareDatetime
    limit: int = Field(default=100, strict=True, ge=1, le=200)


class ReconcileResult(ContractModel):
    stale_before: AwareDatetime
    generations: tuple[Generation, ...]


__all__ = [
    "GenerationBiasSettings",
    "GenerationExecutionResult",
    "GenerationModelSettings",
    "GenerationReportSettings",
    "GenerationRequest",
    "ReconcileResult",
    "RerunGenerationRequest",
    "GenerationRetrySettings",
    "GenerationRunnerSettings",
    "GenerationSettings",
    "GenerationToneSettings",
    "StaleGenerationPolicy",
]
