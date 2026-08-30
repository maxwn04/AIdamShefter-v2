from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, final
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
import pytest

from backend.api.app import create_app
from backend.api.dependencies import get_generation_api_dependencies
from backend.api.dispatch import get_generation_dispatcher
from backend.composition import ApiRuntimeDependencies
from backend.resources.reporting.ai_calls import (
    AICall,
    AICallPage,
    AICallStatus,
    AICallSummary,
    TokenUsage,
)
from backend.resources.reporting.article_overviews import (
    ArticleModelUsage,
    ArticlePage,
    ArticleSummary,
    ArticleUsageSummary,
)
from backend.resources.reporting.artifact_versions import (
    ArtifactVersion,
    ArtifactVersionPage,
    ArtifactVersionSummary,
)
from backend.resources.reporting.artifacts import (
    Artifact,
    ArtifactPage,
    ArtifactSummary,
)
from backend.resources.reporting.generations import (
    Generation,
    GenerationDetail,
    GenerationKind,
    GenerationLifecycleConflict,
    GenerationPage,
    GenerationStatus,
    GenerationSummary,
)
from backend.resources.reporting.memory_recalls import (
    GenerationMemoryRecall,
    MemoryRecallStatus,
)
from backend.resources.reporting.tool_calls import (
    ToolCall,
    ToolCallPage,
    ToolCallStatus,
    ToolCallSummary,
)
from backend.services.model_usage import GenerationUsage, TokenTotals


NOW = datetime(2026, 8, 23, 9, 30, tzinfo=UTC)


@final
class StubRuntime:
    def assert_ready(self) -> None:
        pass

    def close(self) -> None:
        pass


def runtime_factory() -> Callable[[], ApiRuntimeDependencies]:
    return StubRuntime


class StubService:
    def __init__(self, competition_id: UUID, season_id: UUID) -> None:
        self.competition_id = competition_id
        self.season_id = season_id
        self.submissions: list[Any] = []
        self.reruns: list[Any] = []

    def submit(self, request: Any) -> Generation:
        self.submissions.append(request)
        return _generation(
            request.generation_id,
            self.competition_id,
            self.season_id,
        )

    def rerun(self, request: Any) -> Generation:
        self.reruns.append(request)
        return _generation(
            request.generation_id,
            self.competition_id,
            self.season_id,
            rerun_of=request.source_generation_id,
        )


class StubDispatcher:
    def __init__(self) -> None:
        self.dispatched: list[tuple[UUID, UUID]] = []

    def dispatch(self, competition_id: UUID, generation_id: UUID) -> None:
        self.dispatched.append((competition_id, generation_id))


class StubManager:
    def __init__(self, *, exact: object, page: object) -> None:
        self.exact = exact
        self.page = page
        self.get_ids: list[UUID] = []
        self.queries: list[object] = []
        self.error: Exception | None = None

    def get(self, resource_id: UUID) -> object:
        self.get_ids.append(resource_id)
        if self.error is not None:
            raise self.error
        return self.exact

    def list(self, query: object) -> object:
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return self.page


class StubUsage:
    def __init__(self) -> None:
        self.generation_ids: list[UUID] = []

    def get(self, generation_id: UUID) -> GenerationUsage:
        self.generation_ids.append(generation_id)
        return GenerationUsage(
            generation_id=generation_id,
            attempt_count=1,
            latency_ms=10,
            tokens=TokenTotals(input_tokens=100, output_tokens=40, total_tokens=140),
            breakdowns=(),
            estimated_cost="0.0012",
            currency="USD",
            complete=True,
            missing_usage_call_ids=(),
            unpriced_call_ids=(),
            quoted_at=NOW,
        )


def _generation(
    generation_id: UUID,
    competition_id: UUID,
    season_id: UUID,
    *,
    rerun_of: UUID | None = None,
    submitted_version_id: UUID | None = None,
) -> Generation:
    succeeded = submitted_version_id is not None
    return Generation(
        id=generation_id,
        competition_id=competition_id,
        competition_season_id=season_id,
        data_snapshot_id=None,
        input_memory_revision_id=None,
        input_memory_artifact_version_id=None,
        input_memory_artifact_generation_id=None,
        evaluation_workspace_id=None,
        workspace_sequence_number=None,
        rerun_of_generation_id=rerun_of,
        submitted_artifact_version_id=submitted_version_id,
        kind=GenerationKind.LIVE,
        status=(GenerationStatus.SUCCEEDED if succeeded else GenerationStatus.PENDING),
        request_text="weekly recap",
        week_start=8,
        week_end=8,
        domain_cutoff_week=8 if succeeded else None,
        domain_cutoff_at=None,
        knowledge_cutoff_at=NOW if succeeded else None,
        requested_primary_model="gpt-test",
        settings={"schema_version": 1},
        input_manifest={"schema_version": 1} if succeeded else None,
        manifest_schema_version=1 if succeeded else None,
        manifest_hash="a" * 64 if succeeded else None,
        current_turn=3 if succeeded else 0,
        current_stage="complete" if succeeded else None,
        progress_updated_at=NOW if succeeded else None,
        failure_category=None,
        failure_summary=None,
        created_at=NOW,
        started_at=NOW if succeeded else None,
        completed_at=NOW if succeeded else None,
    )


def _summary(generation: Generation) -> GenerationSummary:
    return GenerationSummary.model_validate(
        generation.model_dump(include=set(GenerationSummary.model_fields))
    )


def _dependencies(competition_id: UUID, season_id: UUID) -> SimpleNamespace:
    generation_id = uuid4()
    artifact_id = uuid4()
    version_id = uuid4()
    ai_call_id = uuid4()
    tool_call_id = uuid4()
    generation = GenerationDetail.model_validate(
        _generation(
            generation_id,
            competition_id,
            season_id,
            submitted_version_id=version_id,
        ).model_dump()
    )
    usage = TokenUsage(
        input_tokens=100,
        cached_input_tokens=20,
        output_tokens=40,
        reasoning_tokens=10,
        total_tokens=140,
        raw_provider_usage={"provider_total": 140},
    )
    ai_call = AICall(
        id=ai_call_id,
        generation_id=generation_id,
        turn_number=1,
        attempt_number=0,
        requested_provider=None,
        requested_model="gpt-test",
        actual_provider="test",
        actual_model="gpt-test",
        input_messages=({"role": "user", "content": "recap"},),
        tool_definitions=(),
        request_parameters={},
        provider_response={"id": "safe"},
        status=AICallStatus.SUCCEEDED,
        error=None,
        finish_reason="tool_calls",
        provider_request_id=None,
        provider_response_id="response-1",
        usage=usage,
        started_at=NOW,
        completed_at=NOW,
        latency_ms=10,
    )
    ai_summary = AICallSummary.model_validate(
        ai_call.model_dump(include=set(AICallSummary.model_fields))
    )
    tool_call = ToolCall(
        id=tool_call_id,
        generation_id=generation_id,
        ai_call_id=ai_call_id,
        tool_ordinal=0,
        provider_tool_call_id="tool-1",
        tool_name="get_matchups",
        implementation_version="1",
        arguments={"week": 8},
        status=ToolCallStatus.SUCCEEDED,
        result={"found": True},
        result_text='{"found":true}',
        metadata={"candidate_count": 3},
        error_text=None,
        error=None,
        started_at=NOW,
        completed_at=NOW,
        duration_ms=5,
    )
    tool_summary = ToolCallSummary.model_validate(
        tool_call.model_dump(include=set(ToolCallSummary.model_fields))
    )
    recall = GenerationMemoryRecall(
        generation_id=generation_id,
        status=MemoryRecallStatus.COMPLETE,
        result={
            "context_type": "automatic_reporter_memory",
            "due_callbacks": [],
            "standing_context": [],
            "likely_relevant_memories": [],
            "partial": False,
        },
        result_text=(
            '{"context_type":"automatic_reporter_memory",'
            '"due_callbacks":[],"standing_context":[],'
            '"likely_relevant_memories":[],"partial":false}'
        ),
        metadata={"pinned_revision": 3},
        created_at=NOW,
    )
    artifact = Artifact(
        id=artifact_id,
        generation_id=generation_id,
        path="article.md",
        media_type="text/markdown",
        finalized_version_id=version_id,
        finalized_at=NOW,
        created_at=NOW,
    )
    artifact_summary = ArtifactSummary.model_validate(
        {
            **artifact.model_dump(),
            "revision_count": 2,
            "latest_version_at": NOW,
        }
    )
    version = ArtifactVersion(
        id=version_id,
        artifact_id=artifact_id,
        generation_id=generation_id,
        revision_number=2,
        content="# Final article",
        content_hash="b" * 64,
        source_ai_call_id=ai_call_id,
        source_tool_call_id=tool_call_id,
        created_at=NOW,
    )
    version_summary = ArtifactVersionSummary.model_validate(
        version.model_dump(include=set(ArtifactVersionSummary.model_fields))
    )
    return SimpleNamespace(
        service=StubService(competition_id, season_id),
        dispatcher=StubDispatcher(),
        articles=StubManager(
            exact=generation,
            page=ArticlePage(
                items=(
                    ArticleSummary(
                        generation_id=generation.id,
                        competition_id=competition_id,
                        competition_season_id=season_id,
                        season_year=2026,
                        artifact_id=artifact.id,
                        artifact_path=artifact.path,
                        artifact_media_type=artifact.media_type,
                        submitted_version_id=version.id,
                        submitted_version_revision=version.revision_number,
                        submitted_version_content_hash=version.content_hash,
                        title="Final article",
                        kind=generation.kind,
                        week_start=generation.week_start,
                        week_end=generation.week_end,
                        completed_at=NOW,
                        request_text=generation.request_text,
                        rerun_of_generation_id=generation.rerun_of_generation_id,
                        evaluation_workspace_id=generation.evaluation_workspace_id,
                        workspace_sequence_number=(
                            generation.workspace_sequence_number
                        ),
                        requested_primary_model=(
                            generation.requested_primary_model
                        ),
                        usage=ArticleUsageSummary(
                            models=(
                                ArticleModelUsage(
                                    provider="test",
                                    model="test-model",
                                    attempt_count=1,
                                ),
                            ),
                            attempt_count=1,
                            total_tokens=140,
                            estimated_cost="0.0012",
                            currency="USD",
                            complete=True,
                            quoted_at=NOW,
                        ),
                    ),
                ),
                total=1,
                limit=50,
                offset=0,
            ),
        ),
        generations=StubManager(
            exact=generation,
            page=GenerationPage(
                items=(_summary(generation),), total=1, limit=50, offset=0
            ),
        ),
        ai_calls=StubManager(
            exact=ai_call,
            page=AICallPage(items=(ai_summary,), total=1, limit=50, offset=0),
        ),
        tool_calls=StubManager(
            exact=tool_call,
            page=ToolCallPage(items=(tool_summary,), total=1, limit=50, offset=0),
        ),
        memory_recalls=StubManager(exact=recall, page=None),
        artifacts=StubManager(
            exact=artifact,
            page=ArtifactPage(
                items=(artifact_summary,), total=1, limit=50, offset=0
            ),
        ),
        artifact_versions=StubManager(
            exact=version,
            page=ArtifactVersionPage(
                items=(version_summary,), total=1, limit=50, offset=0
            ),
        ),
        usage=StubUsage(),
    )


async def _client(dependencies: SimpleNamespace) -> tuple[Any, AsyncClient]:
    app = create_app(runtime_factory=runtime_factory())
    app.dependency_overrides[get_generation_api_dependencies] = lambda: dependencies
    app.dependency_overrides[get_generation_dispatcher] = (
        lambda: dependencies.dispatcher
    )
    client = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    )
    return app, client


@pytest.mark.asyncio
async def test_submission_and_rerun_create_pending_requests_without_execution() -> None:
    competition_id = uuid4()
    season_id = uuid4()
    dependencies = _dependencies(competition_id, season_id)
    app, client = await _client(dependencies)
    base = f"/api/v1/generations/competitions/{competition_id}"
    payload = {
        "competition_season_id": str(season_id),
        "kind": "live",
        "request_text": "weekly recap",
        "week_start": 8,
        "week_end": 8,
        "requested_primary_model": "gpt-test",
    }

    async with app.router.lifespan_context(app), client:
        submitted = await client.post(base, json=payload)
        source_id = dependencies.generations.exact.id
        rerun = await client.post(f"{base}/{source_id}/reruns")

    assert submitted.status_code == 201, submitted.text
    assert submitted.json()["generation"]["status"] == "pending"
    assert dependencies.service.submissions[0].competition_id == competition_id
    assert rerun.status_code == 201
    assert rerun.json()["generation"]["rerun_of_generation_id"] == str(source_id)
    assert dependencies.service.reruns[0].source_generation_id == source_id
    submitted_id = UUID(submitted.json()["generation"]["id"])
    rerun_id = UUID(rerun.json()["generation"]["id"])
    assert dependencies.dispatcher.dispatched == [
        (competition_id, submitted_id),
        (competition_id, rerun_id),
    ]


@pytest.mark.asyncio
async def test_submission_rejects_primary_model_duplicated_in_fallbacks() -> None:
    competition_id = uuid4()
    season_id = uuid4()
    dependencies = _dependencies(competition_id, season_id)
    app, client = await _client(dependencies)
    payload = {
        "competition_season_id": str(season_id),
        "kind": "live",
        "request_text": "weekly recap",
        "week_start": 8,
        "week_end": 8,
        "requested_primary_model": " gpt-test ",
        "settings": {"model": {"fallback_models": ["gpt-test"]}},
    }

    async with app.router.lifespan_context(app), client:
        response = await client.post(
            f"/api/v1/generations/competitions/{competition_id}",
            json=payload,
        )

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == (
        "Value error, requested_primary_model cannot duplicate a fallback model"
    )
    assert dependencies.service.submissions == []
    assert dependencies.dispatcher.dispatched == []


@pytest.mark.asyncio
async def test_polling_and_resource_routes_preserve_durable_payloads() -> None:
    competition_id = uuid4()
    season_id = uuid4()
    dependencies = _dependencies(competition_id, season_id)
    generation = dependencies.generations.exact
    artifact = dependencies.artifacts.exact
    base = f"/api/v1/generations/competitions/{competition_id}"
    app, client = await _client(dependencies)

    async with app.router.lifespan_context(app), client:
        history = await client.get(f"{base}?status=succeeded")
        articles = await client.get(f"{base}/articles")
        detail = await client.get(f"{base}/{generation.id}")
        usage_response = await client.get(f"{base}/{generation.id}/usage")
        recall_response = await client.get(
            f"{base}/{generation.id}/memory-recall"
        )
        expected_recall_text = dependencies.memory_recalls.exact.result_text
        dependencies.memory_recalls.exact = None
        legacy_recall_response = await client.get(
            f"{base}/{generation.id}/memory-recall"
        )
        article = await client.get(f"{base}/{generation.id}/article")
        ai_calls = await client.get(f"{base}/{generation.id}/ai-calls")
        ai_call = await client.get(
            f"{base}/{generation.id}/ai-calls/{dependencies.ai_calls.exact.id}"
        )
        tool_call = await client.get(
            f"{base}/{generation.id}/tool-calls/{dependencies.tool_calls.exact.id}"
        )
        artifacts = await client.get(f"{base}/{generation.id}/artifacts")
        versions = await client.get(
            f"{base}/{generation.id}/artifacts/{artifact.id}/versions"
        )
        version = await client.get(
            f"{base}/{generation.id}/artifacts/{artifact.id}/versions/"
            f"{dependencies.artifact_versions.exact.id}"
        )

    assert history.status_code == 200
    assert articles.json()["page"]["items"][0]["title"] == "Final article"
    assert articles.json()["page"]["items"][0]["usage"] == {
        "models": [
            {"provider": "test", "model": "test-model", "attempt_count": 1}
        ],
        "attempt_count": 1,
        "total_tokens": 140,
        "estimated_cost": "0.0012",
        "currency": "USD",
        "complete": True,
        "quoted_at": "2026-08-23T09:30:00Z",
    }
    assert detail.json()["generation"]["input_manifest"] == {"schema_version": 1}
    assert usage_response.json()["usage"]["estimated_cost"] == "0.0012"
    assert dependencies.usage.generation_ids == [generation.id]
    assert recall_response.json()["recall"]["result_text"] == (
        expected_recall_text
    )
    assert recall_response.json()["recall"]["metadata"] == {
        "pinned_revision": 3
    }
    assert legacy_recall_response.json() == {"recall": None}
    assert article.json()["version"]["content"] == "# Final article"
    assert ai_calls.json()["page"]["items"][0]["usage"]["total_tokens"] == 140
    assert ai_call.json()["ai_call"]["usage"]["raw_provider_usage"] == {
        "provider_total": 140
    }
    assert tool_call.json()["tool_call"]["result"] == {"found": True}
    assert tool_call.json()["tool_call"]["result_text"] == '{"found":true}'
    assert tool_call.json()["tool_call"]["metadata"] == {"candidate_count": 3}
    assert "full_result_text" not in tool_call.json()["tool_call"]
    assert "structured_result" not in tool_call.json()["tool_call"]
    assert artifacts.json()["page"]["items"][0]["path"] == "article.md"
    assert artifacts.json()["page"]["items"][0]["revision_count"] == 2
    assert (
        artifacts.json()["page"]["items"][0]["latest_version_at"]
        == "2026-08-23T09:30:00Z"
    )
    assert versions.json()["page"]["items"][0]["revision_number"] == 2
    assert version.json()["version"]["content_hash"] == "b" * 64
    assert dependencies.articles.queries[0].competition_season_id is None


@pytest.mark.asyncio
async def test_child_generation_scope_is_masked_and_conflicts_are_stable() -> None:
    competition_id = uuid4()
    dependencies = _dependencies(competition_id, uuid4())
    generation = dependencies.generations.exact
    dependencies.ai_calls.exact = dependencies.ai_calls.exact.model_copy(
        update={"generation_id": uuid4()}
    )
    base = f"/api/v1/generations/competitions/{competition_id}"
    app, client = await _client(dependencies)

    async with app.router.lifespan_context(app), client:
        masked = await client.get(
            f"{base}/{generation.id}/ai-calls/{dependencies.ai_calls.exact.id}"
        )
        dependencies.generations.error = GenerationLifecycleConflict(
            generation.id,
            "generation is not eligible",
            actual_status="running",
        )
        conflict = await client.get(f"{base}/{generation.id}")

    assert masked.status_code == 404
    assert masked.json()["detail"]["code"] == "reporting_not_found"
    assert conflict.status_code == 409
    assert conflict.json() == {
        "detail": {
            "code": "reporting_conflict",
            "message": "generation is not eligible",
        }
    }


def test_openapi_contains_generation_polling_and_audit_boundaries() -> None:
    paths = set(create_app(runtime_factory=runtime_factory()).openapi()["paths"])
    base = "/api/v1/generations/competitions/{competition_id}"
    generation = f"{base}/{{generation_id}}"

    assert {
        base,
        f"{base}/articles",
        generation,
        f"{generation}/reruns",
        f"{generation}/article",
        f"{generation}/usage",
        f"{generation}/memory-recall",
        f"{generation}/ai-calls",
        f"{generation}/ai-calls/{{ai_call_id}}",
        f"{generation}/tool-calls",
        f"{generation}/tool-calls/{{tool_call_id}}",
        f"{generation}/artifacts",
        f"{generation}/artifacts/{{artifact_id}}",
        f"{generation}/artifacts/{{artifact_id}}/versions",
        f"{generation}/artifacts/{{artifact_id}}/versions/{{version_id}}",
    }.issubset(paths)
