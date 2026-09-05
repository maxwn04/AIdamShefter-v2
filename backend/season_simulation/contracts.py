"""Versioned local campaign contracts; no alternate memory storage."""

from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid5

from pydantic import AwareDatetime, Field, model_validator

from backend.resources._contracts import ContractModel, NonBlankStr
from backend.services.generations.contracts import GenerationSettings
from backend.services.generations.manifest import Sha256


class PreparedStep(ContractModel):
    week: Annotated[int, Field(strict=True, ge=1, le=18)]
    snapshot_id: UUID
    artifact_sha256: Sha256
    input_revision: Sha256
    editorial_cutoff_at: AwareDatetime


class PreparedInputs(ContractModel):
    competition_id: UUID
    competition_season_id: UUID
    season_year: Annotated[int, Field(strict=True, ge=1900, le=9999)]
    data_root: Path
    target_file: Path
    steps: tuple[PreparedStep, ...]
    model: NonBlankStr
    request_template: NonBlankStr = "Write a weekly recap for week {week}."
    settings: GenerationSettings = Field(default_factory=GenerationSettings)

    @model_validator(mode="after")
    def chronology(self) -> "PreparedInputs":
        if not self.steps:
            raise ValueError("a campaign requires steps")
        if self.settings.prepared_execution is not None:
            raise ValueError("prepared execution is assigned separately for each step")
        for index, step in enumerate(self.steps):
            self.request_template.format(week=step.week)
            if step.editorial_cutoff_at.year != self.season_year:
                # NFL season's final weeks may finish the next January.
                if not (step.editorial_cutoff_at.year == self.season_year + 1
                        and step.editorial_cutoff_at.month == 1):
                    raise ValueError("editorial cutoff must belong to the season")
            if index and (step.week <= self.steps[index - 1].week
                          or step.editorial_cutoff_at <= self.steps[index - 1].editorial_cutoff_at):
                raise ValueError("steps require strictly increasing weeks and editorial cutoffs")
        if len({step.snapshot_id for step in self.steps}) != len(self.steps):
            raise ValueError("each step requires a distinct snapshot")
        return self


class RuntimeFreeze(ContractModel):
    files: dict[str, Sha256]
    packages: dict[str, str]
    python: str
    configuration: dict[str, str]
    pricing_sha256: Sha256 = "0" * 64


class Campaign(ContractModel):
    schema_version: Literal[1] = 1
    campaign_id: UUID
    inputs: PreparedInputs
    root_revision_id: UUID
    root_state_hash: NonBlankStr
    target_identity: str
    runtime: RuntimeFreeze

    def generation_id(self, index: int, attempt: int) -> UUID:
        return uuid5(self.campaign_id, f"step:{index}:attempt:{attempt}")


class StepProgress(ContractModel):
    attempts: Annotated[int, Field(strict=True, ge=1)] = 1


class CampaignProgress(ContractModel):
    campaign_hash: Sha256
    steps: tuple[StepProgress, ...]
    state: str = "prepared"
    detail: str | None = None


class RunLimits(ContractModel):
    max_steps: Annotated[int, Field(strict=True, ge=1)] = 1
    max_attempts_per_step: Annotated[int, Field(strict=True, ge=1)] = 1
    max_total_tokens: Annotated[int, Field(strict=True, ge=1)] | None = None
    max_cost: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = None
    max_seconds: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = None
