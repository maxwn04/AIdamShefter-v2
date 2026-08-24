from datetime import UTC, datetime
from uuid import UUID, uuid4

from backend.resources.reporting.ai_calls import (
    AICallPage,
    AICallStatus,
    AICallSummary,
    TokenUsage,
)
from backend.services.model_usage import (
    GenerationUsageService,
    LiteLLMModelRegistry,
    summarize_generation_usage,
)


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
MODEL_MAP = {
    "test/model": {
        "litellm_provider": "test",
        "input_cost_per_token": 0.000001,
        "cache_read_input_token_cost": 0.0000005,
        "output_cost_per_token": 0.000002,
        "output_cost_per_reasoning_token": 0.000003,
    }
}


class StubAICalls:
    def __init__(self, calls: tuple[AICallSummary, ...]) -> None:
        self.calls = calls
        self.offsets: list[int] = []

    def list(self, query) -> AICallPage:
        self.offsets.append(query.offset)
        items = self.calls[query.offset : query.offset + query.limit]
        return AICallPage(
            items=items,
            total=len(self.calls),
            limit=query.limit,
            offset=query.offset,
        )


def _call(
    *,
    model: str | None = "model",
    status: AICallStatus = AICallStatus.SUCCEEDED,
    usage: TokenUsage,
    latency_ms: int = 10,
) -> AICallSummary:
    return AICallSummary(
        id=uuid4(),
        generation_id=GENERATION_ID,
        turn_number=1,
        attempt_number=0,
        requested_provider="test",
        requested_model=model or "requested",
        actual_provider="test" if model is not None else None,
        actual_model=model,
        status=status,
        finish_reason=None,
        usage=usage,
        started_at=NOW,
        completed_at=NOW,
        latency_ms=latency_ms,
    )


GENERATION_ID = UUID("00000000-0000-0000-0000-000000000100")


def _service(calls: tuple[AICallSummary, ...]) -> tuple[GenerationUsageService, StubAICalls]:
    manager = StubAICalls(calls)
    registry = LiteLLMModelRegistry(
        remote_loader=lambda: MODEL_MAP,
        fallback_loader=lambda: {},
    )
    return (
        GenerationUsageService(manager, registry, clock=lambda: NOW),  # type: ignore[arg-type]
        manager,
    )


def test_usage_aggregates_attempts_models_tokens_latency_and_cost() -> None:
    failed = _call(
        status=AICallStatus.RETRYABLE_ERROR,
        usage=TokenUsage(input_tokens=100, output_tokens=0, total_tokens=100),
        latency_ms=10,
    )
    succeeded = _call(
        usage=TokenUsage(
            input_tokens=100,
            cached_input_tokens=20,
            output_tokens=40,
            reasoning_tokens=10,
            total_tokens=140,
        ),
        latency_ms=20,
    )
    service, _ = _service((failed, succeeded))

    result = service.get(GENERATION_ID)

    assert result.attempt_count == 2
    assert result.latency_ms == 30
    assert result.tokens.model_dump() == {
        "input_tokens": 200,
        "cached_input_tokens": 20,
        "output_tokens": 40,
        "reasoning_tokens": 10,
        "total_tokens": 240,
    }
    assert result.estimated_cost == "0.00028"
    assert result.complete is True
    assert result.breakdowns[0].attempt_count == 2
    assert result.breakdowns[0].estimated_cost == "0.00028"


def test_shared_usage_summarizer_matches_service_pricing_semantics() -> None:
    call = _call(
        usage=TokenUsage(
            input_tokens=100,
            cached_input_tokens=20,
            output_tokens=40,
            reasoning_tokens=10,
            total_tokens=140,
        )
    )
    registry = LiteLLMModelRegistry(
        remote_loader=lambda: MODEL_MAP,
        fallback_loader=lambda: {},
    )

    result = summarize_generation_usage(
        GENERATION_ID,
        (call,),
        registry,
        quoted_at=NOW,
    )

    assert result.tokens.total_tokens == 140
    assert result.estimated_cost == "0.00018"
    assert result.complete is True
    assert result.quoted_at == NOW


def test_usage_returns_partial_estimate_and_identifies_affected_calls() -> None:
    priced = _call(usage=TokenUsage(input_tokens=10, output_tokens=0))
    missing = _call(model=None, usage=TokenUsage())
    unknown = _call(model="unknown", usage=TokenUsage(input_tokens=3, output_tokens=1))
    service, _ = _service((priced, missing, unknown))

    result = service.get(GENERATION_ID)

    assert result.estimated_cost == "0.00001"
    assert result.complete is False
    assert result.missing_usage_call_ids == (missing.id,)
    assert result.unpriced_call_ids == (unknown.id,)


def test_usage_pages_through_every_attempt() -> None:
    calls = tuple(
        _call(usage=TokenUsage(input_tokens=1, output_tokens=0))
        for _ in range(201)
    )
    service, manager = _service(calls)

    result = service.get(GENERATION_ID)

    assert result.attempt_count == 201
    assert manager.offsets == [0, 200]


def test_usage_without_attempts_is_not_a_zero_cost_complete_quote() -> None:
    service, _ = _service(())

    result = service.get(GENERATION_ID)

    assert result.attempt_count == 0
    assert result.estimated_cost is None
    assert result.complete is False
