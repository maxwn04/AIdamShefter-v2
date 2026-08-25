"""Set-based article-library query values and projections."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field

from backend.resources._contracts import ContractModel
from backend.resources.reporting.generations import GenerationKind


NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PageLimit = Annotated[int, Field(strict=True, ge=1, le=200)]


class ArticleQuery(ContractModel):
    competition_season_id: UUID | None = None
    kind: GenerationKind | None = None
    limit: PageLimit = 50
    offset: NonNegativeInt = 0


class ArticleModelUsage(ContractModel):
    provider: str | None
    model: str | None
    attempt_count: NonNegativeInt


class ArticleUsageSummary(ContractModel):
    models: tuple[ArticleModelUsage, ...]
    attempt_count: NonNegativeInt
    total_tokens: NonNegativeInt
    estimated_cost: str | None
    currency: str
    complete: bool
    quoted_at: AwareDatetime


class ArticleSummary(ContractModel):
    generation_id: UUID
    competition_id: UUID
    competition_season_id: UUID
    season_year: int
    artifact_id: UUID
    artifact_path: str
    artifact_media_type: str
    submitted_version_id: UUID
    submitted_version_revision: int
    submitted_version_content_hash: str
    title: str
    kind: GenerationKind
    week_start: int | None
    week_end: int | None
    completed_at: AwareDatetime
    request_text: str
    rerun_of_generation_id: UUID | None
    evaluation_workspace_id: UUID | None
    workspace_sequence_number: int | None
    requested_primary_model: str
    usage: ArticleUsageSummary


class ArticlePage(ContractModel):
    items: tuple[ArticleSummary, ...]
    total: NonNegativeInt
    limit: PageLimit
    offset: NonNegativeInt


__all__ = [
    "ArticleModelUsage",
    "ArticlePage",
    "ArticleQuery",
    "ArticleSummary",
    "ArticleUsageSummary",
]
