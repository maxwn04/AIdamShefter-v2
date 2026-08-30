from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from backend.database.sessions import SessionFactory, create_session_factory
from backend.resources.reporting.ai_calls import (
    AICall,
    AICallManager,
    BeginAICall,
    FinishAICall,
)
from backend.resources.reporting.generations import (
    CancelGeneration,
    CreateGeneration,
    GenerationManager,
    StartGeneration,
)
from backend.resources.reporting.tool_calls import (
    BeginToolCall,
    FinishToolCall,
    ToolCallConcurrencyConflict,
    ToolCallLifecycleConflict,
    ToolCallManager,
    ToolCallQuery,
    ToolCallResourceNotFound,
)
from backend.tests.resources.reporting.generations.conftest import (
    GenerationDomain,
    generation_context,
    seed_generation_domain,
)


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
            manifest_hash="b" * 64,
        )
    )
    return manager, generation.id


def _successful_ai_call(
    ai_call_manager: AICallManager,
    generation_id: UUID,
    *,
    turn: int = 1,
) -> AICall:
    started = ai_call_manager.begin_ai_call(
        BeginAICall(
            generation_id=generation_id,
            turn_number=turn,
            requested_model="test-model",
            input_messages=(),
            tool_definitions=(),
            request_parameters={},
        )
    )
    return ai_call_manager.finish_ai_call(
        FinishAICall(
            ai_call_id=started.id,
            status="succeeded",
            actual_model="test-model",
            provider_response={"choices": []},
        )
    )


def _begin(
    generation_id: UUID,
    ai_call_id: UUID,
    *,
    ordinal: int = 0,
) -> BeginToolCall:
    return BeginToolCall(
        generation_id=generation_id,
        ai_call_id=ai_call_id,
        tool_ordinal=ordinal,
        provider_tool_call_id=f"provider-call-{ordinal}",
        tool_name="lookup_matchups",
        implementation_version="v2",
        arguments={"week": 8},
    )


def test_tool_call_lifecycle_preserves_result_text_and_metadata(
    ai_call_manager: AICallManager,
    tool_call_manager: ToolCallManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    _, generation_id = _create_running(session_factory, generation_domain)
    ai_call = _successful_ai_call(ai_call_manager, generation_id)
    started = tool_call_manager.begin_tool_call(_begin(generation_id, ai_call.id))
    assert started.status.value == "running"
    finished = tool_call_manager.finish_tool_call(
        FinishToolCall(
            tool_call_id=started.id,
            status="succeeded",
            result={"found": True, "rows": [1, 2]},
            result_text='{"found": true, "rows": [1, 2]}',
            metadata={"query_id": "private-query"},
        )
    )
    assert finished.result == {"found": True, "rows": [1, 2]}
    assert finished.result_text == '{"found": true, "rows": [1, 2]}'
    assert finished.metadata == {"query_id": "private-query"}
    assert finished.duration_ms is not None
    assert tool_call_manager.get(started.id) == finished
    page = tool_call_manager.list(ToolCallQuery(generation_id=generation_id))
    assert page.total == 1
    assert page.items[0].tool_ordinal == 0


def test_duplicate_provider_ordinal_is_a_typed_conflict(
    ai_call_manager: AICallManager,
    tool_call_manager: ToolCallManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    _, generation_id = _create_running(session_factory, generation_domain)
    ai_call = _successful_ai_call(ai_call_manager, generation_id)
    tool_call_manager.begin_tool_call(_begin(generation_id, ai_call.id))
    with pytest.raises(ToolCallConcurrencyConflict, match="ordinal"):
        tool_call_manager.begin_tool_call(_begin(generation_id, ai_call.id))


def test_tool_provenance_requires_a_successful_same_generation_ai_call(
    ai_call_manager: AICallManager,
    tool_call_manager: ToolCallManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    _, generation_id = _create_running(session_factory, generation_domain)
    started_ai = ai_call_manager.begin_ai_call(
        BeginAICall(
            generation_id=generation_id,
            turn_number=1,
            requested_model="test-model",
            input_messages=(),
            tool_definitions=(),
            request_parameters={},
        )
    )
    with pytest.raises(ToolCallLifecycleConflict, match="succeeded AI call"):
        tool_call_manager.begin_tool_call(_begin(generation_id, started_ai.id))

    _, other_generation_id = _create_running(session_factory, generation_domain)
    with pytest.raises(ToolCallResourceNotFound, match="ai_call"):
        tool_call_manager.begin_tool_call(
            _begin(other_generation_id, started_ai.id)
        )


def test_terminal_parent_blocks_new_tools_but_not_inflight_completion(
    database_engine,
    ai_call_manager: AICallManager,
    tool_call_manager: ToolCallManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    generation_manager, generation_id = _create_running(
        session_factory, generation_domain
    )
    ai_call = _successful_ai_call(ai_call_manager, generation_id)
    inflight = tool_call_manager.begin_tool_call(_begin(generation_id, ai_call.id))
    generation_manager.cancel(CancelGeneration(generation_id=generation_id))
    with pytest.raises(ToolCallLifecycleConflict, match="running generation"):
        tool_call_manager.begin_tool_call(
            _begin(generation_id, ai_call.id, ordinal=1)
        )
    cancelled = tool_call_manager.finish_tool_call(
        FinishToolCall(tool_call_id=inflight.id, status="cancelled")
    )
    assert cancelled.status.value == "cancelled"

    other = seed_generation_domain(database_engine, label="Foreign tool calls")
    foreign_manager = ToolCallManager(
        create_session_factory(database_engine), generation_context(other)
    )
    with pytest.raises(ToolCallResourceNotFound):
        foreign_manager.get(inflight.id)
