"""Strict transport models for generation routes."""

from typing import Annotated, ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.resources._contracts import NonBlankStr
from backend.resources.reporting.ai_calls import AICall, AICallPage
from backend.resources.reporting.article_overviews import ArticlePage
from backend.resources.reporting.artifact_versions import (
    ArtifactVersion,
    ArtifactVersionPage,
)
from backend.resources.reporting.artifacts import Artifact, ArtifactPage
from backend.resources.reporting.generations import (
    Generation,
    GenerationDetail,
    GenerationKind,
    GenerationPage,
)
from backend.resources.reporting.tool_calls import ToolCall, ToolCallPage
from backend.services.generations import GenerationSettings
from backend.services.model_usage import GenerationUsage


PositiveWeek = Annotated[int, Field(strict=True, ge=1, le=18)]


class GenerationApiModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class SubmitGenerationBody(GenerationApiModel):
    competition_season_id: UUID
    kind: GenerationKind
    request_text: NonBlankStr
    week_start: PositiveWeek
    week_end: PositiveWeek
    requested_primary_model: NonBlankStr
    settings: GenerationSettings = Field(default_factory=GenerationSettings)

    @model_validator(mode="after")
    def validate_submission(self) -> "SubmitGenerationBody":
        if self.week_start > self.week_end:
            raise ValueError("week_start cannot be after week_end")
        if self.requested_primary_model in self.settings.model.fallback_models:
            raise ValueError(
                "requested_primary_model cannot duplicate a fallback model"
            )
        return self


class GenerationResponse(GenerationApiModel):
    generation: Generation


class GenerationDetailResponse(GenerationApiModel):
    generation: GenerationDetail


class GenerationPageResponse(GenerationApiModel):
    page: GenerationPage


class ArticlePageResponse(GenerationApiModel):
    page: ArticlePage


class GenerationUsageResponse(GenerationApiModel):
    usage: GenerationUsage


class AICallResponse(GenerationApiModel):
    ai_call: AICall


class AICallPageResponse(GenerationApiModel):
    page: AICallPage


class ToolCallResponse(GenerationApiModel):
    tool_call: ToolCall


class ToolCallPageResponse(GenerationApiModel):
    page: ToolCallPage


class ArtifactResponse(GenerationApiModel):
    artifact: Artifact


class ArtifactPageResponse(GenerationApiModel):
    page: ArtifactPage


class ArtifactVersionResponse(GenerationApiModel):
    version: ArtifactVersion


class ArtifactVersionPageResponse(GenerationApiModel):
    page: ArtifactVersionPage


class SubmittedArticleResponse(GenerationApiModel):
    generation: GenerationDetail
    artifact: Artifact
    version: ArtifactVersion

