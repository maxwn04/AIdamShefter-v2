"""PostgreSQL integration for completion attempts through the durable recorder."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from backend.database.sessions import SessionFactory
from backend.resources.reporting.ai_calls import AICallManager, AICallQuery
from backend.resources.reporting.generations import (
    CreateGeneration,
    GenerationManager,
    StartGeneration,
)
from backend.services.generations import GenerationExecutionRecorder
from backend.services.reporter.runner.completion import (
    CompletionClient,
    CompletionSettings,
    RetryPolicy,
)
from backend.tests.resources.reporting.generations.conftest import (
    GenerationDomain,
    generation_context,
)


class RateLimitError(Exception):
    status_code = 429


def _create_running_generation(
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
            requested_primary_model="primary",
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


def test_retry_and_fallback_round_trip_as_sequential_durable_attempts(
    ai_call_manager: AICallManager,
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> None:
    generation_id = _create_running_generation(session_factory, generation_domain)
    outcomes: list[Any] = [
        RateLimitError("primary unavailable"),
        {
            "id": "response-1",
            "model": "fallback",
            "provider": "test",
            "choices": [{"finish_reason": "stop"}],
            "usage": {"input_tokens": 9, "output_tokens": 4},
        },
    ]

    async def complete(**_kwargs: Any) -> Any:
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    recorder = GenerationExecutionRecorder(generation_id, ai_call_manager)
    client = CompletionClient(
        complete,
        CompletionSettings(
            model="primary",
            fallback_models=("fallback",),
            retry=RetryPolicy(max_retries=0),
        ),
        recorder,
    )

    response = asyncio.run(client.complete(turn_number=1, messages=[]))

    assert response["id"] == "response-1"
    page = ai_call_manager.list(AICallQuery(generation_id=generation_id))
    assert [item.attempt_number for item in page.items] == [0, 1]
    assert [item.status.value for item in page.items] == [
        "retryable_error",
        "succeeded",
    ]
    assert page.items[1].usage.input_tokens == 9
    assert page.items[1].usage.output_tokens == 4
    assert recorder.successful_ai_call_id(1) == page.items[1].id
