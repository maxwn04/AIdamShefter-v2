from datetime import UTC, datetime
from uuid import uuid4

from backend.resources.reporting.memory_recalls import (
    GenerationMemoryRecall,
    MemoryRecallStatus,
    RecordGenerationMemoryRecall,
)


def test_memory_recall_contract_preserves_public_result_and_private_metadata() -> None:
    generation_id = uuid4()
    command = RecordGenerationMemoryRecall(
        generation_id=generation_id,
        status="partial",
        result={"context_type": "automatic_reporter_memory", "partial": True},
        result_text='{"context_type":"automatic_reporter_memory"}',
        metadata={"pinned_revision": 9},
    )
    recall = GenerationMemoryRecall(
        **command.model_dump(),
        created_at=datetime(2026, 8, 30, tzinfo=UTC),
    )

    assert recall.status is MemoryRecallStatus.PARTIAL
    assert recall.result["partial"] is True
    assert recall.result_text == command.result_text
    assert recall.metadata == {"pinned_revision": 9}
