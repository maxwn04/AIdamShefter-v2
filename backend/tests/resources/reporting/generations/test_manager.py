from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.reporting import (
    Artifact,
    ArtifactVersion,
    EvaluationWorkspace,
    Generation as StoredGeneration,
)
from backend.database.sessions import create_session_factory
from backend.resources.reporting.generations import (
    CancelGeneration,
    CreateGeneration,
    FailGeneration,
    GenerationConcurrencyConflict,
    GenerationLifecycleConflict,
    GenerationManager,
    GenerationQuery,
    GenerationResourceNotFound,
    StartGeneration,
    UpdateGenerationProgress,
)
from backend.tests.resources.reporting.generations.conftest import (
    GenerationDomain,
    generation_context,
    seed_generation_domain,
)


def _create_command(
    domain: GenerationDomain,
    *,
    generation_id: UUID | None = None,
    **overrides: object,
) -> CreateGeneration:
    values: dict[str, object] = {
        "generation_id": generation_id or uuid4(),
        "competition_season_id": domain.season_id,
        "kind": "live",
        "request_text": "write a weekly recap",
        "week_start": 8,
        "week_end": 8,
        "requested_primary_model": "test-model",
        "settings": {"fallbacks": ["backup-model"]},
    }
    values.update(overrides)
    return CreateGeneration.model_validate(values)


def _start_command(
    domain: GenerationDomain,
    generation_id: UUID,
) -> StartGeneration:
    return StartGeneration(
        generation_id=generation_id,
        data_snapshot_id=domain.snapshot_id,
        input_memory_revision_id=domain.memory_revision_id,
        knowledge_cutoff_at=datetime(2026, 10, 27, tzinfo=UTC),
        input_manifest={"prompt_hash": "b" * 64},
        manifest_schema_version=1,
        manifest_hash="c" * 64,
    )


def test_pending_start_progress_and_terminal_lifecycle_are_atomic(
    generation_manager: GenerationManager,
    generation_domain: GenerationDomain,
) -> None:
    pending = generation_manager.create_pending(_create_command(generation_domain))
    assert pending.status.value == "pending"
    assert pending.data_snapshot_id is None
    assert pending.settings == {"fallbacks": ["backup-model"]}

    running = generation_manager.start(_start_command(generation_domain, pending.id))
    assert running.status.value == "running"
    assert running.data_snapshot_id == generation_domain.snapshot_id
    assert running.domain_cutoff_week == 8
    assert running.domain_cutoff_at is None
    assert running.input_memory_revision_id == generation_domain.memory_revision_id
    assert running.input_manifest == {"prompt_hash": "b" * 64}
    assert running.manifest_hash == "c" * 64

    with pytest.raises(GenerationLifecycleConflict):
        generation_manager.start(_start_command(generation_domain, pending.id))
    progressed = generation_manager.update_progress(
        UpdateGenerationProgress(
            generation_id=pending.id,
            current_turn=3,
            current_stage="drafting",
        )
    )
    assert progressed.current_turn == 3
    with pytest.raises(GenerationLifecycleConflict, match="earlier turn"):
        generation_manager.update_progress(
            UpdateGenerationProgress(
                generation_id=pending.id,
                current_turn=2,
                current_stage="research",
            )
        )
    failed = generation_manager.fail(
        FailGeneration(
            generation_id=pending.id,
            category="provider_error",
            summary="Provider failed after retries",
        )
    )
    assert failed.status.value == "failed"
    assert failed.completed_at is not None
    with pytest.raises(GenerationLifecycleConflict):
        generation_manager.cancel(CancelGeneration(generation_id=pending.id))
    assert (
        generation_manager.get(pending.id).data_snapshot_id
        == running.data_snapshot_id
    )


def test_failed_start_rolls_back_all_input_pinning(
    database_engine: Engine,
    generation_manager: GenerationManager,
    generation_domain: GenerationDomain,
) -> None:
    other = seed_generation_domain(database_engine, label="Foreign input")
    pending = generation_manager.create_pending(_create_command(generation_domain))
    command = _start_command(generation_domain, pending.id).model_copy(
        update={"input_memory_revision_id": other.memory_revision_id}
    )
    with pytest.raises(GenerationResourceNotFound, match="memory_revision"):
        generation_manager.start(command)
    stored = generation_manager.get(pending.id)
    assert stored.status.value == "pending"
    assert stored.data_snapshot_id is None
    assert stored.input_manifest is None


def test_reads_reruns_and_history_are_competition_scoped(
    database_engine: Engine,
    generation_manager: GenerationManager,
    generation_domain: GenerationDomain,
) -> None:
    original = generation_manager.create_pending(_create_command(generation_domain))
    rerun_command = _create_command(
        generation_domain,
        rerun_of_generation_id=original.id,
    )
    with pytest.raises(GenerationLifecycleConflict, match="terminal source"):
        generation_manager.create_pending(rerun_command)
    generation_manager.cancel(CancelGeneration(generation_id=original.id))
    rerun = generation_manager.create_pending(rerun_command)
    page = generation_manager.list(
        GenerationQuery(rerun_of_generation_id=original.id, limit=1)
    )
    assert page.total == 1
    assert page.items[0].id == rerun.id
    history = generation_manager.list(GenerationQuery(limit=1))
    assert history.total == 2
    assert history.items[0].id == rerun.id
    assert generation_manager.list(GenerationQuery(limit=1, offset=1)).items[
        0
    ].id == original.id

    other = seed_generation_domain(database_engine, label="Other competition")
    other_manager = GenerationManager(
        create_session_factory(database_engine), generation_context(other)
    )
    with pytest.raises(GenerationResourceNotFound):
        other_manager.get(original.id)
    with pytest.raises(GenerationResourceNotFound):
        other_manager.create_pending(
            _create_command(other, rerun_of_generation_id=original.id)
        )


def test_concurrent_pending_identity_has_one_typed_winner(
    generation_manager: GenerationManager,
    generation_domain: GenerationDomain,
) -> None:
    command = _create_command(generation_domain)

    def create(_: int):
        try:
            return generation_manager.create_pending(command)
        except GenerationConcurrencyConflict as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(create, range(2)))
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert (
        sum(isinstance(result, GenerationConcurrencyConflict) for result in results)
        == 1
    )


def test_workspace_generation_pins_only_the_current_succeeded_artifact(
    database_engine: Engine,
    generation_manager: GenerationManager,
    generation_domain: GenerationDomain,
) -> None:
    workspace_id = uuid4()
    source_generation_id = uuid4()
    artifact_id = uuid4()
    version_id = uuid4()
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(EvaluationWorkspace),
            {
                "id": workspace_id,
                "competition_id": generation_domain.competition_id,
                "base_memory_revision_id": generation_domain.memory_revision_id,
                "status": "active",
            },
        )
        connection.execute(
            sa.insert(StoredGeneration),
            {
                "id": source_generation_id,
                "competition_id": generation_domain.competition_id,
                "competition_season_id": generation_domain.season_id,
                "evaluation_workspace_id": workspace_id,
                "workspace_sequence_number": 1,
                "kind": "backtest",
                "status": "succeeded",
                "request_text": "source",
                "requested_primary_model": "test-model",
                "settings_jsonb": {},
                "current_turn": 1,
            },
        )
        connection.execute(
            sa.insert(Artifact),
            {
                "id": artifact_id,
                "generation_id": source_generation_id,
                "path": "memory/workspace.json",
                "media_type": "application/json",
            },
        )
        connection.execute(
            sa.insert(ArtifactVersion),
            {
                "id": version_id,
                "artifact_id": artifact_id,
                "generation_id": source_generation_id,
                "revision_number": 1,
                "content": "{}",
                "content_hash": (
                    "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
                ),
            },
        )
        connection.execute(
            sa.update(EvaluationWorkspace)
            .where(EvaluationWorkspace.id == workspace_id)
            .values(
                current_memory_artifact_version_id=version_id,
                current_memory_artifact_generation_id=source_generation_id,
            )
        )

    pending = generation_manager.create_pending(
        _create_command(
            generation_domain,
            kind="backtest",
            evaluation_workspace_id=workspace_id,
            workspace_sequence_number=2,
        )
    )
    start = _start_command(generation_domain, pending.id).model_copy(
        update={
            "input_memory_revision_id": None,
            "input_memory_artifact_version_id": version_id,
            "input_memory_artifact_generation_id": source_generation_id,
        }
    )
    running = generation_manager.start(start)
    assert running.input_memory_revision_id is None
    assert running.input_memory_artifact_version_id == version_id
