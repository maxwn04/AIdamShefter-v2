from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from backend.database.sessions import SessionFactory, create_session_factory
from backend.resources.reporting.generations import (
    CreateGeneration,
    GenerationConcurrencyConflict,
    GenerationLifecycleConflict,
    GenerationManager,
    GenerationResourceNotFound,
    StartGeneration,
)
from backend.resources.reporting.memory_recalls import (
    GenerationMemoryRecallManager,
    RecordGenerationMemoryRecall,
)
from backend.tests.resources.reporting.generations.conftest import (
    GenerationDomain,
    generation_context,
    seed_generation_domain,
)


def _create_generation(
    session_factory: SessionFactory,
    domain: GenerationDomain,
    *,
    running: bool,
) -> UUID:
    manager = GenerationManager(session_factory, generation_context(domain))
    generation = manager.create_pending(
        CreateGeneration(
            generation_id=uuid4(),
            competition_season_id=domain.season_id,
            kind="live",
            request_text="write the recap",
            requested_primary_model="test-model",
            settings={},
        )
    )
    if running:
        manager.start(
            StartGeneration(
                generation_id=generation.id,
                data_snapshot_id=domain.snapshot_id,
                input_memory_revision_id=domain.memory_revision_id,
                knowledge_cutoff_at=datetime(2026, 10, 27, tzinfo=UTC),
                input_manifest={"schema": 1},
                manifest_schema_version=1,
                manifest_hash="c" * 64,
            )
        )
    return generation.id


def _command(generation_id: UUID) -> RecordGenerationMemoryRecall:
    return RecordGenerationMemoryRecall(
        generation_id=generation_id,
        status="complete",
        result={
            "context_type": "automatic_reporter_memory",
            "due_callbacks": [],
            "standing_context": [],
            "likely_relevant_memories": [],
            "partial": False,
        },
        result_text='{"context_type":"automatic_reporter_memory"}',
        metadata={"pinned_revision": 7},
    )


def test_record_and_get_preserve_exact_text_and_metadata(
    memory_recall_manager: GenerationMemoryRecallManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    generation_id = _create_generation(
        session_factory,
        generation_domain,
        running=True,
    )
    recorded = memory_recall_manager.record(_command(generation_id))

    assert recorded.result_text == '{"context_type":"automatic_reporter_memory"}'
    assert recorded.metadata == {"pinned_revision": 7}
    assert memory_recall_manager.get(generation_id) == recorded

    with pytest.raises(GenerationConcurrencyConflict, match="already recorded"):
        memory_recall_manager.record(_command(generation_id))


def test_legacy_pending_generation_returns_none_and_cannot_record(
    memory_recall_manager: GenerationMemoryRecallManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    generation_id = _create_generation(
        session_factory,
        generation_domain,
        running=False,
    )

    assert memory_recall_manager.get(generation_id) is None
    with pytest.raises(GenerationLifecycleConflict, match="running generation"):
        memory_recall_manager.record(_command(generation_id))


def test_recall_is_competition_scoped_and_immutable(
    database_engine,
    memory_recall_manager: GenerationMemoryRecallManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    generation_id = _create_generation(
        session_factory,
        generation_domain,
        running=True,
    )
    memory_recall_manager.record(_command(generation_id))
    foreign = seed_generation_domain(database_engine, label="Foreign Recall")
    foreign_manager = GenerationMemoryRecallManager(
        create_session_factory(database_engine),
        generation_context(foreign),
    )

    with pytest.raises(GenerationResourceNotFound):
        foreign_manager.get(generation_id)
    with pytest.raises(
        DBAPIError,
        match="generation memory recall records are immutable",
    ):
        with database_engine.begin() as connection:
            connection.execute(
                sa.text(
                    "UPDATE reporting.generation_memory_recalls "
                    "SET result_text = 'changed' WHERE generation_id = :id"
                ),
                {"id": generation_id},
            )
