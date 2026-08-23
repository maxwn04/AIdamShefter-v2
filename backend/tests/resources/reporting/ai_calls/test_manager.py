from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from backend.database.sessions import SessionFactory, create_session_factory
from backend.resources.reporting.ai_calls import (
    AICallConcurrencyConflict,
    AICallLifecycleConflict,
    AICallManager,
    AICallQuery,
    AICallResourceNotFound,
    BeginAICall,
    FinishAICall,
    TokenUsage,
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


def _begin(generation_id: UUID, *, turn: int = 1) -> BeginAICall:
    return BeginAICall(
        generation_id=generation_id,
        turn_number=turn,
        requested_provider="test-provider",
        requested_model="requested-model",
        input_messages=({"role": "user", "content": "hello"},),
        tool_definitions=({"type": "function", "name": "lookup"},),
        request_parameters={"temperature": 0.1},
    )


def _success(call_id: UUID) -> FinishAICall:
    return FinishAICall(
        ai_call_id=call_id,
        status="succeeded",
        actual_provider="actual-provider",
        actual_model="actual-model",
        provider_response={"choices": [{"finish_reason": "tool_calls"}]},
        finish_reason="tool_calls",
        provider_request_id="request-1",
        provider_response_id="response-1",
        usage=TokenUsage(
            input_tokens=20,
            cached_input_tokens=3,
            output_tokens=8,
            reasoning_tokens=2,
            total_tokens=28,
            raw_provider_usage={"prompt_tokens": 20, "completion_tokens": 8},
        ),
    )


def test_attempts_finish_and_read_back_exact_telemetry(
    ai_call_manager: AICallManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    _, generation_id = _create_running(session_factory, generation_domain)
    first = ai_call_manager.begin_ai_call(_begin(generation_id))
    assert first.attempt_number == 0
    retry = ai_call_manager.finish_ai_call(
        FinishAICall(
            ai_call_id=first.id,
            status="retryable_error",
            actual_provider="test-provider",
            error={"type": "timeout"},
        )
    )
    assert retry.status.value == "retryable_error"

    second = ai_call_manager.begin_ai_call(_begin(generation_id))
    assert second.attempt_number == 1
    succeeded = ai_call_manager.finish_ai_call(_success(second.id))
    assert succeeded.provider_response == {
        "choices": [{"finish_reason": "tool_calls"}]
    }
    assert succeeded.usage.cached_input_tokens == 3
    assert succeeded.usage.raw_provider_usage == {
        "prompt_tokens": 20,
        "completion_tokens": 8,
    }
    assert succeeded.completed_at is not None
    assert succeeded.latency_ms is not None

    page = ai_call_manager.list(AICallQuery(generation_id=generation_id))
    assert page.total == 2
    assert [item.attempt_number for item in page.items] == [0, 1]
    assert ai_call_manager.get(second.id) == succeeded


def test_concurrent_attempt_allocation_is_sequential(
    ai_call_manager: AICallManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    _, generation_id = _create_running(session_factory, generation_domain)
    with ThreadPoolExecutor(max_workers=2) as pool:
        calls = tuple(
            pool.map(
                lambda _: ai_call_manager.begin_ai_call(_begin(generation_id)),
                range(2),
            )
        )
    assert sorted(call.attempt_number for call in calls) == [0, 1]


def test_only_one_success_per_turn_is_a_typed_conflict(
    ai_call_manager: AICallManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    _, generation_id = _create_running(session_factory, generation_domain)
    first = ai_call_manager.begin_ai_call(_begin(generation_id))
    second = ai_call_manager.begin_ai_call(_begin(generation_id))
    ai_call_manager.finish_ai_call(_success(first.id))
    with pytest.raises(AICallConcurrencyConflict, match="already recorded"):
        ai_call_manager.finish_ai_call(_success(second.id))


def test_terminal_parent_blocks_new_calls_but_not_inflight_completion(
    database_engine,
    ai_call_manager: AICallManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    generation_manager, generation_id = _create_running(
        session_factory, generation_domain
    )
    inflight = ai_call_manager.begin_ai_call(_begin(generation_id))
    generation_manager.cancel(CancelGeneration(generation_id=generation_id))
    with pytest.raises(AICallLifecycleConflict, match="running generation"):
        ai_call_manager.begin_ai_call(_begin(generation_id, turn=2))
    finished = ai_call_manager.finish_ai_call(
        FinishAICall(ai_call_id=inflight.id, status="cancelled")
    )
    assert finished.status.value == "cancelled"
    with pytest.raises(AICallLifecycleConflict, match="started"):
        ai_call_manager.finish_ai_call(
            FinishAICall(ai_call_id=inflight.id, status="cancelled")
        )

    other = seed_generation_domain(database_engine, label="Foreign AI calls")
    foreign_manager = AICallManager(
        create_session_factory(database_engine), generation_context(other)
    )
    with pytest.raises(AICallResourceNotFound):
        foreign_manager.get(inflight.id)
