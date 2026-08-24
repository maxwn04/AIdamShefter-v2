"""Aggregate durable model attempts into one generation usage estimate."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from backend.resources.reporting.ai_calls import (
    AICallManager,
    AICallQuery,
    AICallSummary,
    TokenUsage,
)
from backend.services.model_usage.objects import (
    GenerationUsage,
    ModelUsageBreakdown,
    TokenTotals,
)
from backend.services.model_usage.pricing import LiteLLMModelRegistry


Clock = Callable[[], datetime]


@dataclass(slots=True)
class _Accumulator:
    provider: str | None
    model: str | None
    attempts: int = 0
    latency_ms: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    cost: Decimal = field(default_factory=Decimal)
    priced_attempts: int = 0
    complete: bool = True

    def add_usage(self, usage: TokenUsage) -> None:
        self.input_tokens += usage.input_tokens or 0
        self.cached_input_tokens += usage.cached_input_tokens or 0
        self.output_tokens += usage.output_tokens or 0
        self.reasoning_tokens += usage.reasoning_tokens or 0
        if usage.total_tokens is not None:
            self.total_tokens += usage.total_tokens
        elif usage.input_tokens is not None and usage.output_tokens is not None:
            self.total_tokens += usage.input_tokens + usage.output_tokens

    def tokens(self) -> TokenTotals:
        return TokenTotals(
            input_tokens=self.input_tokens,
            cached_input_tokens=self.cached_input_tokens,
            output_tokens=self.output_tokens,
            reasoning_tokens=self.reasoning_tokens,
            total_tokens=self.total_tokens,
        )


class GenerationUsageService:
    def __init__(
        self,
        ai_calls: AICallManager,
        registry: LiteLLMModelRegistry,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._ai_calls = ai_calls
        self._registry = registry
        self._clock = clock or (lambda: datetime.now(UTC))

    def get(self, generation_id: UUID) -> GenerationUsage:
        calls = self._all_calls(generation_id)
        return summarize_generation_usage(
            generation_id,
            calls,
            self._registry,
            quoted_at=self._clock(),
        )

    def _all_calls(self, generation_id: UUID) -> tuple[AICallSummary, ...]:
        collected: list[AICallSummary] = []
        offset = 0
        while True:
            page = self._ai_calls.list(
                AICallQuery(
                    generation_id=generation_id,
                    limit=200,
                    offset=offset,
                )
            )
            collected.extend(page.items)
            offset += len(page.items)
            if offset >= page.total or not page.items:
                break
        return tuple(collected)


def summarize_generation_usage(
    generation_id: UUID,
    calls: tuple[AICallSummary, ...],
    registry: LiteLLMModelRegistry,
    *,
    quoted_at: datetime,
) -> GenerationUsage:
    """Aggregate an already-bounded call set with canonical pricing semantics."""

    total = _Accumulator(provider=None, model=None)
    groups: dict[tuple[str | None, str | None], _Accumulator] = {}
    missing_usage: list[UUID] = []
    unpriced: list[UUID] = []

    for call in calls:
        key = (call.actual_provider, call.actual_model)
        group = groups.setdefault(
            key,
            _Accumulator(provider=key[0], model=key[1]),
        )
        for accumulator in (total, group):
            accumulator.attempts += 1
            accumulator.latency_ms += call.latency_ms or 0
            accumulator.add_usage(call.usage)

        usage_complete = (
            call.usage.input_tokens is not None
            and call.usage.output_tokens is not None
        )
        if not usage_complete:
            missing_usage.append(call.id)
            total.complete = False
            group.complete = False

        has_priceable_usage = (
            call.usage.input_tokens is not None
            or call.usage.output_tokens is not None
        )
        quote = None
        if has_priceable_usage and call.actual_model is not None:
            quote = registry.quote(
                call.actual_provider,
                call.actual_model,
                call.usage,
            )
        if has_priceable_usage and quote is None:
            unpriced.append(call.id)
            total.complete = False
            group.complete = False
        elif quote is not None:
            total.cost += quote
            total.priced_attempts += 1
            group.cost += quote
            group.priced_attempts += 1

    breakdowns = tuple(
        ModelUsageBreakdown(
            provider=group.provider,
            model=group.model,
            attempt_count=group.attempts,
            latency_ms=group.latency_ms,
            tokens=group.tokens(),
            estimated_cost=(
                _decimal_string(group.cost) if group.priced_attempts > 0 else None
            ),
            currency="USD",
            complete=group.complete,
        )
        for group in groups.values()
    )
    return GenerationUsage(
        generation_id=generation_id,
        attempt_count=total.attempts,
        latency_ms=total.latency_ms,
        tokens=total.tokens(),
        breakdowns=breakdowns,
        estimated_cost=(
            _decimal_string(total.cost) if total.priced_attempts > 0 else None
        ),
        currency="USD",
        complete=bool(calls) and total.complete,
        missing_usage_call_ids=tuple(missing_usage),
        unpriced_call_ids=tuple(unpriced),
        quoted_at=quoted_at,
    )


def _decimal_string(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return format(normalized, "f")
    return format(normalized, "f")
