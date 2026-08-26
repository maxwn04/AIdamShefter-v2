from datetime import UTC, datetime
import hashlib
from uuid import UUID, uuid4

import pytest

from backend.database.sessions import SessionFactory, create_session_factory
from backend.resources.reporting.artifact_versions import (
    AppendArtifactVersion,
    ArtifactVersionManager,
)
from backend.resources.reporting.artifacts import (
    ArtifactConcurrencyConflict,
    ArtifactLifecycleConflict,
    ArtifactManager,
    ArtifactMediaTypeConflict,
    ArtifactQuery,
    ArtifactResourceNotFound,
    CreateArtifact,
    FinalizeArtifact,
)
from backend.resources.reporting.generations import (
    CancelGeneration,
    CreateGeneration,
    GenerationManager,
    StartGeneration,
)
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
) -> tuple[GenerationManager, UUID]:
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
    return manager, generation.id


def _create(
    manager: ArtifactManager,
    generation_id: UUID,
    *,
    path: str = "article.md",
    media_type: str = "text/markdown",
):
    return manager.create_artifact(
        CreateArtifact(
            generation_id=generation_id,
            path=path,
            media_type=media_type,
        )
    )


def test_create_is_idempotent_and_media_type_is_immutable(
    artifact_manager: ArtifactManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    _, generation_id = _create_running(session_factory, generation_domain)
    created = _create(artifact_manager, generation_id)
    repeated = _create(artifact_manager, generation_id)
    assert repeated == created
    with pytest.raises(ArtifactMediaTypeConflict, match="already uses"):
        _create(
            artifact_manager,
            generation_id,
            media_type="text/plain",
        )


def test_list_orders_paths_and_filters_finalized_artifacts(
    artifact_manager: ArtifactManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    _, generation_id = _create_running(session_factory, generation_domain)
    _create(artifact_manager, generation_id, path="research_brief.md")
    article = _create(artifact_manager, generation_id)
    version_manager = ArtifactVersionManager(
        session_factory, generation_context(generation_domain)
    )
    version_manager.append_artifact_version(
        AppendArtifactVersion(
            artifact_id=article.id,
            content="# Article draft",
            content_hash=_hash("# Article draft"),
        )
    )
    version = version_manager.append_artifact_version(
        AppendArtifactVersion(
            artifact_id=article.id,
            content="# Article final",
            content_hash=_hash("# Article final"),
        )
    )
    artifact_manager.finalize_artifact(
        FinalizeArtifact(artifact_id=article.id, artifact_version_id=version.id)
    )
    page = artifact_manager.list(ArtifactQuery(generation_id=generation_id))
    assert [item.path for item in page.items] == [
        "article.md",
        "research_brief.md",
    ]
    assert page.items[0].revision_count == 2
    assert page.items[0].latest_version_at == version.created_at
    assert page.items[1].revision_count == 0
    assert page.items[1].latest_version_at is None
    finalized = artifact_manager.list(
        ArtifactQuery(generation_id=generation_id, finalized=True)
    )
    assert finalized.total == 1
    assert finalized.items[0].id == article.id


def test_finalization_selects_latest_version_and_is_idempotent(
    artifact_manager: ArtifactManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    _, generation_id = _create_running(session_factory, generation_domain)
    artifact = _create(artifact_manager, generation_id)
    version_manager = ArtifactVersionManager(
        session_factory, generation_context(generation_domain)
    )
    first = version_manager.append_artifact_version(
        AppendArtifactVersion(
            artifact_id=artifact.id,
            content="first",
            content_hash=_hash("first"),
        )
    )
    second = version_manager.append_artifact_version(
        AppendArtifactVersion(
            artifact_id=artifact.id,
            content="second",
            content_hash=_hash("second"),
        )
    )
    with pytest.raises(ArtifactConcurrencyConflict, match="latest"):
        artifact_manager.finalize_artifact(
            FinalizeArtifact(artifact_id=artifact.id, artifact_version_id=first.id)
        )
    finalized = artifact_manager.finalize_artifact(
        FinalizeArtifact(artifact_id=artifact.id, artifact_version_id=second.id)
    )
    assert finalized.finalized_version_id == second.id
    assert finalized.finalized_at is not None
    assert (
        artifact_manager.finalize_artifact(
            FinalizeArtifact(artifact_id=artifact.id, artifact_version_id=second.id)
        )
        == finalized
    )


def test_generation_lifecycle_and_competition_scope_are_enforced(
    database_engine,
    artifact_manager: ArtifactManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    generation_manager, generation_id = _create_running(
        session_factory, generation_domain
    )
    artifact = _create(artifact_manager, generation_id)
    generation_manager.cancel(CancelGeneration(generation_id=generation_id))
    with pytest.raises(ArtifactLifecycleConflict, match="running generation"):
        _create(artifact_manager, generation_id, path="late.md")

    foreign_domain = seed_generation_domain(database_engine, label="Foreign Artifact")
    foreign = ArtifactManager(
        create_session_factory(database_engine), generation_context(foreign_domain)
    )
    with pytest.raises(ArtifactResourceNotFound):
        foreign.get(artifact.id)
