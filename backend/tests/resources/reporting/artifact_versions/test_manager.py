from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import hashlib
from uuid import UUID, uuid4

import pytest

from backend.database.sessions import SessionFactory, create_session_factory
from backend.resources.reporting.ai_calls import (
    AICallManager,
    BeginAICall,
    FinishAICall,
)
from backend.resources.reporting.artifact_versions import (
    AppendArtifactVersion,
    ArtifactVersionLifecycleConflict,
    ArtifactVersionManager,
    ArtifactVersionProvenanceConflict,
    ArtifactVersionQuery,
    ArtifactVersionResourceNotFound,
)
from backend.resources.reporting.artifacts import (
    ArtifactManager,
    CreateArtifact,
    FinalizeArtifact,
)
from backend.resources.reporting.generations import (
    CreateGeneration,
    GenerationManager,
    StartGeneration,
)
from backend.resources.reporting.tool_calls import BeginToolCall, ToolCallManager
from backend.tests.resources.reporting.generations.conftest import (
    GenerationDomain,
    generation_context,
    seed_generation_domain,
)


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _create_running(
    session_factory: SessionFactory,
    domain: GenerationDomain,
) -> UUID:
    manager = GenerationManager(session_factory, generation_context(domain))
    generation = manager.create_pending(
        CreateGeneration(
            generation_id=uuid4(),
            competition_season_id=domain.season_id,
            kind="live",
            request_text="write the recap",
            week_start=8,
            week_end=8,
            requested_primary_model="test-model",
            settings={},
        )
    )
    manager.start(
        StartGeneration(
            generation_id=generation.id,
            data_snapshot_id=domain.snapshot_id,
            input_memory_revision_id=domain.memory_revision_id,
            knowledge_cutoff_at=datetime(2026, 10, 27, tzinfo=UTC),
            input_manifest={"schema": 1},
            manifest_schema_version=1,
            manifest_hash="a" * 64,
        )
    )
    return generation.id


def _create_artifact(
    session_factory: SessionFactory,
    domain: GenerationDomain,
    generation_id: UUID,
):
    manager = ArtifactManager(session_factory, generation_context(domain))
    return manager.create_artifact(
        CreateArtifact(
            generation_id=generation_id,
            path="article.md",
            media_type="text/markdown",
        )
    )


def _append(artifact_id: UUID, content: str) -> AppendArtifactVersion:
    return AppendArtifactVersion(
        artifact_id=artifact_id,
        content=content,
        content_hash=_hash(content),
    )


def _successful_ai_call(
    session_factory: SessionFactory,
    domain: GenerationDomain,
    generation_id: UUID,
):
    manager = AICallManager(session_factory, generation_context(domain))
    started = manager.begin_ai_call(
        BeginAICall(
            generation_id=generation_id,
            turn_number=1,
            requested_model="test-model",
            input_messages=(),
            tool_definitions=(),
            request_parameters={},
        )
    )
    return manager.finish_ai_call(
        FinishAICall(
            ai_call_id=started.id,
            status="succeeded",
            actual_model="test-model",
            provider_response={"choices": []},
        )
    )


def test_append_allocates_revisions_and_lists_without_full_content(
    artifact_version_manager: ArtifactVersionManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    generation_id = _create_running(session_factory, generation_domain)
    artifact = _create_artifact(
        session_factory, generation_domain, generation_id
    )
    first = artifact_version_manager.append_artifact_version(
        _append(artifact.id, "first")
    )
    second = artifact_version_manager.append_artifact_version(
        _append(artifact.id, "second")
    )
    assert (first.revision_number, second.revision_number) == (1, 2)
    assert artifact_version_manager.get(second.id).content == "second"
    page = artifact_version_manager.list(
        ArtifactVersionQuery(artifact_id=artifact.id)
    )
    assert page.total == 2
    assert [item.revision_number for item in page.items] == [1, 2]
    assert "content" not in page.items[0].model_fields_set


def test_identical_writes_are_idempotent_including_under_concurrency(
    artifact_version_manager: ArtifactVersionManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    generation_id = _create_running(session_factory, generation_domain)
    artifact = _create_artifact(
        session_factory, generation_domain, generation_id
    )
    command = _append(artifact.id, "same snapshot")
    with ThreadPoolExecutor(max_workers=2) as pool:
        versions = tuple(
            pool.map(
                lambda _: artifact_version_manager.append_artifact_version(command),
                range(2),
            )
        )
    assert versions[0] == versions[1]
    assert versions[0].revision_number == 1


def test_concurrent_distinct_writes_receive_sequential_revisions(
    artifact_version_manager: ArtifactVersionManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    generation_id = _create_running(session_factory, generation_domain)
    artifact = _create_artifact(
        session_factory, generation_domain, generation_id
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        versions = tuple(
            pool.map(
                lambda content: artifact_version_manager.append_artifact_version(
                    _append(artifact.id, content)
                ),
                ("alpha", "beta"),
            )
        )
    assert sorted(version.revision_number for version in versions) == [1, 2]


def test_provenance_must_belong_to_the_artifact_generation(
    database_engine,
    artifact_version_manager: ArtifactVersionManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    generation_id = _create_running(session_factory, generation_domain)
    artifact = _create_artifact(
        session_factory, generation_domain, generation_id
    )
    ai_call = _successful_ai_call(
        session_factory, generation_domain, generation_id
    )
    tool_manager = ToolCallManager(
        session_factory, generation_context(generation_domain)
    )
    tool_call = tool_manager.begin_tool_call(
        BeginToolCall(
            generation_id=generation_id,
            ai_call_id=ai_call.id,
            tool_ordinal=0,
            tool_name="create_artifact",
            implementation_version="v1",
            arguments={},
        )
    )
    recorded = artifact_version_manager.append_artifact_version(
        AppendArtifactVersion(
            **_append(artifact.id, "with provenance").model_dump(
                exclude={"source_ai_call_id", "source_tool_call_id"}
            ),
            source_ai_call_id=ai_call.id,
            source_tool_call_id=tool_call.id,
        )
    )
    assert recorded.source_tool_call_id == tool_call.id

    other_domain = seed_generation_domain(database_engine, label="Foreign Version")
    other_factory = create_session_factory(database_engine)
    other_generation_id = _create_running(other_factory, other_domain)
    foreign_ai_call = _successful_ai_call(
        other_factory, other_domain, other_generation_id
    )
    with pytest.raises(ArtifactVersionResourceNotFound, match="ai_call"):
        artifact_version_manager.append_artifact_version(
            AppendArtifactVersion(
                **_append(artifact.id, "with provenance").model_dump(
                    exclude={"source_ai_call_id", "source_tool_call_id"}
                ),
                source_ai_call_id=foreign_ai_call.id,
            )
        )

    second_ai = AICallManager(
        session_factory, generation_context(generation_domain)
    ).begin_ai_call(
        BeginAICall(
            generation_id=generation_id,
            turn_number=2,
            requested_model="test-model",
            input_messages=(),
            tool_definitions=(),
            request_parameters={},
        )
    )
    with pytest.raises(ArtifactVersionProvenanceConflict, match="source AI"):
        artifact_version_manager.append_artifact_version(
            AppendArtifactVersion(
                **_append(artifact.id, "mixed provenance").model_dump(
                    exclude={"source_ai_call_id", "source_tool_call_id"}
                ),
                source_ai_call_id=second_ai.id,
                source_tool_call_id=tool_call.id,
            )
        )


def test_finalized_artifacts_reject_appends_and_scope_is_masked(
    database_engine,
    artifact_version_manager: ArtifactVersionManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    generation_id = _create_running(session_factory, generation_domain)
    artifact = _create_artifact(
        session_factory, generation_domain, generation_id
    )
    version = artifact_version_manager.append_artifact_version(
        _append(artifact.id, "final")
    )
    ArtifactManager(
        session_factory, generation_context(generation_domain)
    ).finalize_artifact(
        FinalizeArtifact(
            artifact_id=artifact.id,
            artifact_version_id=version.id,
        )
    )
    with pytest.raises(ArtifactVersionLifecycleConflict, match="finalized"):
        artifact_version_manager.append_artifact_version(
            _append(artifact.id, "too late")
        )

    foreign_domain = seed_generation_domain(database_engine, label="Foreign Reader")
    foreign = ArtifactVersionManager(
        create_session_factory(database_engine), generation_context(foreign_domain)
    )
    with pytest.raises(ArtifactVersionResourceNotFound):
        foreign.get(version.id)
