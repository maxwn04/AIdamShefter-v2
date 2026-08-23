from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from uuid import uuid4

import pytest
import sqlalchemy as sa
from pydantic import TypeAdapter
from sqlalchemy.engine import Engine

from backend.database.models.memory import CurrentRevision, MemoryRevision
from backend.database.models.reporting import Artifact, Generation as StoredGeneration
from backend.database.sessions import create_session_factory
from backend.resources.memory.common import MemoryKind
from backend.resources.memory.context_notes import (
    ContextNoteContent,
    ContextNoteIdentity,
)
from backend.resources.reporting.artifact_versions import (
    AppendArtifactVersion,
    ArtifactVersionManager,
    ArtifactVersionQuery,
)
from backend.resources.reporting.artifacts import ArtifactManager, CreateArtifact
from backend.resources.reporting.generations import (
    CreateGeneration,
    GenerationManager,
    StartGeneration,
)
from backend.services.generations import GenerationFinalizer
from backend.services.memory import (
    MemoryMutationBundle,
    MemoryMutationMetadata,
    MemoryProposal,
)
from backend.services.reporter import ReporterOutput
from backend.services.reporter.runner.schemas import ArtifactSnapshot
from backend.tests.database.conftest import database_engine, migrated_database
from backend.tests.resources.reporting.generations.conftest import (
    generation_context,
    seed_generation_domain,
)


KNOWLEDGE_CUTOFF = datetime(2026, 10, 27, 20, tzinfo=UTC)
ARTICLE = "# Final article\n"
ARTICLE_HASH = hashlib.sha256(ARTICLE.encode()).hexdigest()


def _running_generation(engine: Engine, *, kind: str = "live"):
    domain = seed_generation_domain(engine, label=f"Finalization {kind}")
    factory = create_session_factory(engine)
    context = generation_context(domain)
    generations = GenerationManager(factory, context)
    pending = generations.create_pending(
        CreateGeneration(
            generation_id=uuid4(),
            competition_season_id=domain.season_id,
            kind=kind,
            request_text="write the final article",
            week_start=8,
            week_end=8,
            requested_primary_model="test-model",
            settings={},
        )
    )
    running = generations.start(
        StartGeneration(
            generation_id=pending.id,
            data_snapshot_id=domain.snapshot_id,
            input_memory_revision_id=domain.memory_revision_id,
            knowledge_cutoff_at=KNOWLEDGE_CUTOFF,
            input_manifest={"version": 1},
            manifest_schema_version=1,
            manifest_hash="a" * 64,
        )
    )
    artifacts = ArtifactManager(factory, context)
    artifact_versions = ArtifactVersionManager(factory, context)
    artifact = artifacts.create_artifact(
        CreateArtifact(
            generation_id=running.id,
            path="columns/week-8.md",
            media_type="text/markdown",
        )
    )
    version = artifact_versions.append_artifact_version(
        AppendArtifactVersion(
            artifact_id=artifact.id,
            content=ARTICLE,
            content_hash=ARTICLE_HASH,
        )
    )
    output = ReporterOutput(
        submitted_path=artifact.path,
        artifacts=(
            ArtifactSnapshot(
                path=artifact.path,
                content=ARTICLE,
                revision=version.revision_number,
                content_hash=ARTICLE_HASH,
            ),
        ),
    )
    return domain, factory, context, generations, running, artifact, version, output


def _bundle(domain, generation_id, *, proposals=()) -> MemoryMutationBundle:
    return MemoryMutationBundle(
        competition_id=domain.competition_id,
        generation_id=generation_id,
        expected_revision_id=domain.memory_revision_id,
        competition_season_id=domain.season_id,
        week=8,
        knowledge_cutoff_at=KNOWLEDGE_CUTOFF,
        proposals=proposals,
    )


def _context_note_proposal() -> MemoryProposal:
    return MemoryProposal(
        proposal_id=uuid4(),
        operation="create",
        kind=MemoryKind.CONTEXT_NOTE,
        item_id=uuid4(),
        version_id=uuid4(),
        context_note_identity=TypeAdapter(ContextNoteIdentity).validate_python(
            {"scope": "competition", "note_key": "weekly-form"}
        ),
        content=ContextNoteContent.model_validate(
            {
                "narrative": "The league's playoff race tightened this week.",
                "outlook": "Expect aggressive waiver moves.",
                "status": "active",
                "tags": ["playoffs"],
            }
        ),
        metadata=MemoryMutationMetadata(change_reason="generation finalization"),
    )


def test_empty_live_bundle_finalizes_existing_version_without_copy(
    database_engine: Engine,
) -> None:
    domain, factory, context, generations, running, artifact, version, output = (
        _running_generation(database_engine)
    )
    finalizer = GenerationFinalizer(factory, context)

    result = finalizer.finalize(running.id, output, _bundle(domain, running.id))

    assert result.generation.status.value == "succeeded"
    assert result.generation.submitted_artifact_version_id == version.id
    assert result.memory_result is not None
    assert result.memory_result.revision is None
    assert ArtifactManager(factory, context).get(artifact.id).finalized_version_id == version.id
    assert ArtifactVersionManager(factory, context).list(
        ArtifactVersionQuery(artifact_id=artifact.id)
    ).total == 1
    assert generations.get(running.id).status.value == "succeeded"


def test_live_bundle_commits_one_generation_owned_canonical_revision(
    database_engine: Engine,
) -> None:
    domain, factory, context, generations, running, _, version, output = (
        _running_generation(database_engine)
    )
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(CurrentRevision),
            {
                "competition_id": domain.competition_id,
                "current_revision_id": domain.memory_revision_id,
                "lock_version": 0,
            },
        )
    proposal = _context_note_proposal()

    result = GenerationFinalizer(factory, context).finalize(
        running.id,
        output,
        _bundle(domain, running.id, proposals=(proposal,)),
    )

    assert result.generation.status.value == "succeeded"
    assert result.generation.submitted_artifact_version_id == version.id
    assert result.memory_result is not None
    assert result.memory_result.revision is not None
    assert result.memory_result.revision.producing_generation_id == running.id
    assert result.memory_result.changes == (proposal.proposed_ref(),)
    assert generations.get(running.id).status.value == "succeeded"


def test_live_memory_and_reporting_commit_roll_back_together_on_late_failure(
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain, factory, context, generations, running, artifact, _, output = (
        _running_generation(database_engine)
    )
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(CurrentRevision),
            {
                "competition_id": domain.competition_id,
                "current_revision_id": domain.memory_revision_id,
                "lock_version": 0,
            },
        )
    proposal = _context_note_proposal()
    finalizer = GenerationFinalizer(factory, context)

    def fail_after_memory(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("injected terminal write failure")

    monkeypatch.setattr(
        "backend.services.generations.finalization._succeed_generation_in_session",
        fail_after_memory,
    )
    with pytest.raises(RuntimeError, match="injected terminal"):
        finalizer.finalize(
            running.id,
            output,
            _bundle(domain, running.id, proposals=(proposal,)),
        )

    with database_engine.begin() as connection:
        finalized_version_id = connection.execute(
            sa.select(Artifact.finalized_version_id).where(Artifact.id == artifact.id)
        ).scalar_one()
        generation_status, submitted_version_id = connection.execute(
            sa.select(
                StoredGeneration.status,
                StoredGeneration.submitted_artifact_version_id,
            ).where(StoredGeneration.id == running.id)
        ).one()
        current = connection.execute(
            sa.select(CurrentRevision.current_revision_id).where(
                CurrentRevision.competition_id == domain.competition_id
            )
        ).scalar_one()
        produced = connection.execute(
            sa.select(sa.func.count()).select_from(MemoryRevision).where(
                MemoryRevision.producing_generation_id == running.id
            )
        ).scalar_one()
    assert finalized_version_id is None
    assert generation_status == "running"
    assert submitted_version_id is None
    assert current == domain.memory_revision_id
    assert produced == 0


def test_backtest_discards_empty_bundle_and_rejects_memory_proposals(
    database_engine: Engine,
) -> None:
    domain, factory, context, generations, running, artifact, version, output = (
        _running_generation(database_engine, kind="backtest")
    )
    finalizer = GenerationFinalizer(factory, context)

    with pytest.raises(RuntimeError, match="backtest generations"):
        finalizer.finalize(
            running.id,
            output,
            _bundle(domain, running.id, proposals=(_context_note_proposal(),)),
        )

    assert generations.get(running.id).status.value == "running"
    assert ArtifactManager(factory, context).get(artifact.id).finalized_version_id is None
    result = finalizer.finalize(running.id, output, _bundle(domain, running.id))
    assert result.generation.status.value == "succeeded"
    assert result.generation.submitted_artifact_version_id == version.id
    assert result.memory_result is None


def test_missing_or_mismatched_submission_leaves_running_outputs_unchanged(
    database_engine: Engine,
) -> None:
    domain, factory, context, generations, running, artifact, _, _ = (
        _running_generation(database_engine)
    )
    finalizer = GenerationFinalizer(factory, context)

    with pytest.raises(RuntimeError, match="select one submitted artifact"):
        finalizer.finalize(
            running.id,
            ReporterOutput(),
            _bundle(domain, running.id),
        )
    changed = "# Changed after recording\n"
    mismatch = ReporterOutput(
        submitted_path=artifact.path,
        artifacts=(
            ArtifactSnapshot(
                path=artifact.path,
                content=changed,
                revision=1,
                content_hash=hashlib.sha256(changed.encode()).hexdigest(),
            ),
        ),
    )
    with pytest.raises(RuntimeError, match="does not match"):
        finalizer.finalize(
            running.id,
            mismatch,
            _bundle(domain, running.id),
        )

    assert generations.get(running.id).status.value == "running"
    assert ArtifactManager(factory, context).get(artifact.id).finalized_version_id is None
