"""Bounded, set-based reader for one competition's submitted articles."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import html
import re
from typing import cast
from uuid import UUID

import sqlalchemy as sa

from backend.database.models.core import CompetitionSeason as StoredSeason
from backend.database.models.reporting import AICall as StoredAICall
from backend.database.models.reporting import Artifact as StoredArtifact
from backend.database.models.reporting import ArtifactVersion as StoredArtifactVersion
from backend.database.models.reporting import Generation as StoredGeneration
from backend.database.sessions import SessionFactory, read_only_session
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.reporting.ai_calls import AICallSummary, TokenUsage
from backend.resources.reporting.article_overviews.objects import (
    ArticleModelUsage,
    ArticlePage,
    ArticleQuery,
    ArticleSummary,
    ArticleUsageSummary,
)
from backend.resources.reporting.generations import GenerationStatus
from backend.services.model_usage import LiteLLMModelRegistry
from backend.services.model_usage.usage import summarize_generation_usage


Clock = Callable[[], datetime]
UNTITLED_ARTICLE = "Untitled article"
_H1 = re.compile(r"^ {0,3}#[\t ]+(.+?)(?:[\t ]+#+[\t ]*)?$")
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_MARKDOWN_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_CODE_SPAN = re.compile(r"`+([^`]*)`+")
_HTML_TAG = re.compile(r"<[^>]+>")


class ArticleOverviewReader:
    """Read one article page without issuing child requests per row."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
        registry: LiteLLMModelRegistry,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id
        self._registry = registry
        self._clock = clock or (lambda: datetime.now(UTC))

    def list(self, query: ArticleQuery) -> ArticlePage:
        conditions: list[sa.ColumnElement[bool]] = [
            StoredGeneration.competition_id == self._competition_id,
            StoredGeneration.status == GenerationStatus.SUCCEEDED.value,
            StoredGeneration.submitted_artifact_version_id.is_not(None),
        ]
        if query.competition_season_id is not None:
            conditions.append(
                StoredGeneration.competition_season_id
                == query.competition_season_id
            )
        if query.kind is not None:
            conditions.append(StoredGeneration.kind == query.kind.value)

        with read_only_session(self._session_factory) as session:
            total = cast(
                int,
                session.scalar(
                    sa.select(sa.func.count())
                    .select_from(StoredGeneration)
                    .where(*conditions)
                ),
            )
            rows = session.execute(
                sa.select(
                    StoredGeneration.id,
                    StoredGeneration.competition_id,
                    StoredGeneration.competition_season_id,
                    StoredGeneration.kind,
                    StoredGeneration.week_start,
                    StoredGeneration.week_end,
                    StoredGeneration.completed_at,
                    StoredGeneration.request_text,
                    StoredGeneration.rerun_of_generation_id,
                    StoredGeneration.evaluation_workspace_id,
                    StoredGeneration.workspace_sequence_number,
                    StoredGeneration.requested_primary_model,
                    StoredSeason.season_year.label("season_year"),
                    StoredArtifact.id,
                    StoredArtifact.path,
                    StoredArtifact.media_type,
                    StoredArtifactVersion.id,
                    StoredArtifactVersion.revision_number,
                    StoredArtifactVersion.content_hash,
                    StoredArtifactVersion.content,
                )
                .join(
                    StoredSeason,
                    sa.and_(
                        StoredSeason.id == StoredGeneration.competition_season_id,
                        StoredSeason.competition_id
                        == StoredGeneration.competition_id,
                    ),
                )
                .join(
                    StoredArtifactVersion,
                    sa.and_(
                        StoredArtifactVersion.id
                        == StoredGeneration.submitted_artifact_version_id,
                        StoredArtifactVersion.generation_id == StoredGeneration.id,
                    ),
                )
                .join(
                    StoredArtifact,
                    sa.and_(
                        StoredArtifact.id == StoredArtifactVersion.artifact_id,
                        StoredArtifact.generation_id == StoredGeneration.id,
                        StoredArtifact.finalized_version_id
                        == StoredArtifactVersion.id,
                    ),
                )
                .where(*conditions)
                .order_by(
                    StoredGeneration.completed_at.desc(),
                    StoredGeneration.id.desc(),
                )
                .limit(query.limit)
                .offset(query.offset)
            ).all()

            generation_ids = tuple(
                row._mapping[StoredGeneration.id] for row in rows
            )
            calls_by_generation: dict[UUID, list[AICallSummary]] = {
                generation_id: [] for generation_id in generation_ids
            }
            if generation_ids:
                call_rows = session.execute(
                    sa.select(
                        StoredAICall.id,
                        StoredAICall.generation_id,
                        StoredAICall.turn_number,
                        StoredAICall.attempt_number,
                        StoredAICall.requested_provider,
                        StoredAICall.requested_model,
                        StoredAICall.actual_provider,
                        StoredAICall.actual_model,
                        StoredAICall.status,
                        StoredAICall.finish_reason,
                        StoredAICall.input_tokens,
                        StoredAICall.cached_input_tokens,
                        StoredAICall.output_tokens,
                        StoredAICall.reasoning_tokens,
                        StoredAICall.total_tokens,
                        StoredAICall.started_at,
                        StoredAICall.completed_at,
                        StoredAICall.latency_ms,
                    )
                    .join(
                        StoredGeneration,
                        StoredGeneration.id == StoredAICall.generation_id,
                    )
                    .where(
                        StoredGeneration.competition_id == self._competition_id,
                        StoredAICall.generation_id.in_(generation_ids),
                    )
                    .order_by(
                        StoredAICall.generation_id.asc(),
                        StoredAICall.turn_number.asc(),
                        StoredAICall.attempt_number.asc(),
                    )
                ).all()
                for call_row in call_rows:
                    generation_id = call_row._mapping[StoredAICall.generation_id]
                    calls_by_generation[generation_id].append(
                        _decode_call_summary(call_row)
                    )

        quoted_at = self._clock()
        items = tuple(
            self._decode_article(
                row,
                tuple(calls_by_generation[row._mapping[StoredGeneration.id]]),
                quoted_at,
            )
            for row in rows
        )
        return ArticlePage(
            items=items,
            total=total,
            limit=query.limit,
            offset=query.offset,
        )

    def _decode_article(
        self,
        row: sa.Row[tuple[object, ...]],
        calls: tuple[AICallSummary, ...],
        quoted_at: datetime,
    ) -> ArticleSummary:
        values = row._mapping
        generation_id = values[StoredGeneration.id]
        usage = summarize_generation_usage(
            generation_id,
            calls,
            self._registry,
            quoted_at=quoted_at,
        )
        completed_at = values[StoredGeneration.completed_at]
        if completed_at is None:
            raise ValueError("submitted generation requires completed_at")
        return ArticleSummary(
            generation_id=generation_id,
            competition_id=values[StoredGeneration.competition_id],
            competition_season_id=values[StoredGeneration.competition_season_id],
            season_year=values["season_year"],
            artifact_id=values[StoredArtifact.id],
            artifact_path=values[StoredArtifact.path],
            artifact_media_type=values[StoredArtifact.media_type],
            submitted_version_id=values[StoredArtifactVersion.id],
            submitted_version_revision=values[
                StoredArtifactVersion.revision_number
            ],
            submitted_version_content_hash=values[
                StoredArtifactVersion.content_hash
            ],
            title=derive_article_title(values[StoredArtifactVersion.content]),
            kind=values[StoredGeneration.kind],
            week_start=values[StoredGeneration.week_start],
            week_end=values[StoredGeneration.week_end],
            completed_at=completed_at,
            request_text=values[StoredGeneration.request_text],
            rerun_of_generation_id=values[
                StoredGeneration.rerun_of_generation_id
            ],
            evaluation_workspace_id=values[
                StoredGeneration.evaluation_workspace_id
            ],
            workspace_sequence_number=values[
                StoredGeneration.workspace_sequence_number
            ],
            requested_primary_model=values[
                StoredGeneration.requested_primary_model
            ],
            usage=ArticleUsageSummary(
                models=tuple(
                    ArticleModelUsage(
                        provider=breakdown.provider,
                        model=breakdown.model,
                        attempt_count=breakdown.attempt_count,
                    )
                    for breakdown in usage.breakdowns
                ),
                attempt_count=usage.attempt_count,
                total_tokens=usage.tokens.total_tokens,
                estimated_cost=usage.estimated_cost,
                currency=usage.currency,
                complete=usage.complete,
                quoted_at=usage.quoted_at,
            ),
        )


def derive_article_title(markdown: str) -> str:
    """Return the first non-fenced Markdown H1 or the stable fallback."""

    fence_character: str | None = None
    fence_length = 0
    for line in markdown.splitlines():
        fence = _FENCE_OPEN.match(line)
        if fence_character is None and fence is not None:
            marker = fence.group(1)
            fence_character = marker[0]
            fence_length = len(marker)
            continue
        if fence_character is not None:
            closing_fence = re.fullmatch(
                rf" {{0,3}}{re.escape(fence_character)}{{{fence_length},}}[\t ]*",
                line,
            )
            if closing_fence is not None:
                fence_character = None
                fence_length = 0
            continue
        heading = _H1.match(line)
        if heading is not None:
            title = _plain_heading_text(heading.group(1))
            if title:
                return title
    return UNTITLED_ARTICLE


def _plain_heading_text(markdown: str) -> str:
    title = _MARKDOWN_LINK.sub(r"\1", markdown)
    title = _CODE_SPAN.sub(r"\1", title)
    title = _HTML_TAG.sub("", title)
    title = re.sub(r"(?<!\\)[*_~]", "", title)
    title = re.sub(r"\\([\\`*{}\[\]()#+.!_>~-])", r"\1", title)
    return html.unescape(title).strip()


def _decode_call_summary(
    row: sa.Row[tuple[object, ...]],
) -> AICallSummary:
    values = row._mapping
    return AICallSummary(
        id=values[StoredAICall.id],
        generation_id=values[StoredAICall.generation_id],
        turn_number=values[StoredAICall.turn_number],
        attempt_number=values[StoredAICall.attempt_number],
        requested_provider=values[StoredAICall.requested_provider],
        requested_model=values[StoredAICall.requested_model],
        actual_provider=values[StoredAICall.actual_provider],
        actual_model=values[StoredAICall.actual_model],
        status=values[StoredAICall.status],
        finish_reason=values[StoredAICall.finish_reason],
        usage=TokenUsage(
            input_tokens=values[StoredAICall.input_tokens],
            cached_input_tokens=values[StoredAICall.cached_input_tokens],
            output_tokens=values[StoredAICall.output_tokens],
            reasoning_tokens=values[StoredAICall.reasoning_tokens],
            total_tokens=values[StoredAICall.total_tokens],
        ),
        started_at=values[StoredAICall.started_at],
        completed_at=values[StoredAICall.completed_at],
        latency_ms=values[StoredAICall.latency_ms],
    )


__all__ = ["ArticleOverviewReader", "derive_article_title"]
