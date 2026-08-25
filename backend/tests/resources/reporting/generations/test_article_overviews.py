from datetime import UTC, datetime
import hashlib
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.engine import Engine

from backend.database.models.reporting import AICall, Artifact, ArtifactVersion
from backend.database.sessions import SessionFactory
from backend.resources.reporting.article_overviews import (
    ArticleOverviewReader,
    ArticleQuery,
    derive_article_title,
)
from backend.resources.reporting.generations import (
    CreateGeneration,
    GenerationManager,
    StartGeneration,
    SucceedGeneration,
)
from backend.services.model_usage import LiteLLMModelRegistry
from backend.tests.resources.reporting.generations.conftest import (
    GenerationDomain,
    generation_context,
)


NOW = datetime(2026, 11, 4, 12, 30, tzinfo=UTC)
MODEL_MAP = {
    "test/model": {
        "litellm_provider": "test",
        "input_cost_per_token": 0.000001,
        "output_cost_per_token": 0.000002,
    }
}


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("# The real headline\n\nBody", "The real headline"),
        ("Intro\n\n# Headline with closing hashes ##\n", "Headline with closing hashes"),
        ("```md\n# Not the title\n```\n# Actual title", "Actual title"),
        (
            "```md\n```not a closing fence\n# Still fenced\n```\n"
            "# **Plain** [title](https://example.com)",
            "Plain title",
        ),
        ("## A section only\n\nBody", "Untitled article"),
    ],
)
def test_article_title_uses_first_non_fenced_h1(
    markdown: str,
    expected: str,
) -> None:
    assert derive_article_title(markdown) == expected


def test_article_reader_joins_exact_submission_and_batches_priced_usage(
    database_engine: Engine,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
    generation_manager: GenerationManager,
) -> None:
    generation = generation_manager.create_pending(
        CreateGeneration(
            generation_id=uuid4(),
            competition_season_id=generation_domain.season_id,
            kind="live",
            request_text="Write the definitive week-eight recap",
            week_start=8,
            week_end=8,
            requested_primary_model="test/model",
            settings={},
        )
    )
    generation_manager.start(
        StartGeneration(
            generation_id=generation.id,
            data_snapshot_id=generation_domain.snapshot_id,
            input_memory_revision_id=generation_domain.memory_revision_id,
            knowledge_cutoff_at=NOW,
            input_manifest={"schema_version": 1},
            manifest_schema_version=1,
            manifest_hash="a" * 64,
        )
    )
    artifact_id = uuid4()
    version_id = uuid4()
    content = "# Eight Is Enough\n\nThe week belonged to the underdogs."
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(Artifact),
            {
                "id": artifact_id,
                "generation_id": generation.id,
                "path": "custom/final.md",
                "media_type": "text/markdown",
            },
        )
        connection.execute(
            sa.insert(ArtifactVersion),
            {
                "id": version_id,
                "artifact_id": artifact_id,
                "generation_id": generation.id,
                "revision_number": 2,
                "content": content,
                "content_hash": hashlib.sha256(content.encode()).hexdigest(),
            },
        )
        connection.execute(
            sa.update(Artifact)
            .where(Artifact.id == artifact_id)
            .values(finalized_version_id=version_id, finalized_at=NOW)
        )
    generation_manager.succeed(
        SucceedGeneration(
            generation_id=generation.id,
            submitted_artifact_version_id=version_id,
        )
    )
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(AICall),
            {
                "id": uuid4(),
                "generation_id": generation.id,
                "turn_number": 1,
                "attempt_number": 0,
                "requested_provider": "test",
                "requested_model": "model",
                "actual_provider": "test",
                "actual_model": "model",
                "input_messages": [{"role": "user", "content": "large body"}],
                "tool_definitions": [{"name": "unused-large-body"}],
                "request_parameters": {},
                "provider_response": {"content": "not selected by projection"},
                "status": "succeeded",
                "finish_reason": "stop",
                "input_tokens": 100,
                "cached_input_tokens": 0,
                "output_tokens": 20,
                "reasoning_tokens": 0,
                "total_tokens": 120,
                "started_at": NOW,
                "completed_at": NOW,
                "latency_ms": 10,
            },
        )

    registry = LiteLLMModelRegistry(
        remote_loader=lambda: MODEL_MAP,
        fallback_loader=lambda: {},
    )
    reader = ArticleOverviewReader(
        session_factory,
        generation_context(generation_domain),
        registry,
        clock=lambda: NOW,
    )
    selected_statements: list[str] = []

    def record_selects(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            selected_statements.append(statement)

    event.listen(database_engine, "before_cursor_execute", record_selects)
    try:
        page = reader.list(ArticleQuery(limit=10))
    finally:
        event.remove(database_engine, "before_cursor_execute", record_selects)

    assert len(selected_statements) == 3
    assert page.total == 1
    article = page.items[0]
    assert article.generation_id == generation.id
    assert article.season_year == 2026
    assert article.artifact_id == artifact_id
    assert article.submitted_version_id == version_id
    assert article.title == "Eight Is Enough"
    assert article.request_text == "Write the definitive week-eight recap"
    assert article.usage.total_tokens == 120
    assert article.usage.estimated_cost == "0.00014"
    assert article.usage.complete is True
    assert article.usage.models[0].model == "model"
    assert article.usage.quoted_at == NOW

    assert reader.list(ArticleQuery(kind="backtest")).items == ()
