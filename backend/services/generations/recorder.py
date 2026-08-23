"""Durable generation-scoped adapter for reporter completion attempts."""

from __future__ import annotations

from uuid import UUID

from backend.resources.reporting.ai_calls import (
    AICallManager,
    BeginAICall,
    FinishAICall,
    TokenUsage,
)
from backend.services.reporter.runner.recording import (
    ModelAttemptFinish,
    ModelAttemptStart,
)


class GenerationExecutionRecorder:
    """Translate reporter completion events into durable AI-call resources."""

    def __init__(self, generation_id: UUID, manager: AICallManager) -> None:
        self._generation_id = generation_id
        self._manager = manager
        self._successful_by_turn: dict[int, UUID] = {}

    @property
    def generation_id(self) -> UUID:
        return self._generation_id

    def begin_model_attempt(self, attempt: ModelAttemptStart) -> UUID:
        started = self._manager.begin_ai_call(
            BeginAICall(
                generation_id=self._generation_id,
                turn_number=attempt.turn_number,
                requested_provider=attempt.requested_provider,
                requested_model=attempt.requested_model,
                input_messages=attempt.input_messages,
                tool_definitions=attempt.tool_definitions,
                request_parameters=attempt.request_parameters,
            )
        )
        return started.id

    def finish_model_attempt(
        self,
        attempt_id: UUID,
        result: ModelAttemptFinish,
    ) -> None:
        finished = self._manager.finish_ai_call(
            FinishAICall(
                ai_call_id=attempt_id,
                status=result.status,
                actual_provider=result.actual_provider,
                actual_model=result.actual_model,
                provider_response=result.provider_response,
                error=result.error,
                finish_reason=result.finish_reason,
                provider_request_id=result.provider_request_id,
                provider_response_id=result.provider_response_id,
                usage=TokenUsage(
                    input_tokens=result.usage.input_tokens,
                    cached_input_tokens=result.usage.cached_input_tokens,
                    output_tokens=result.usage.output_tokens,
                    reasoning_tokens=result.usage.reasoning_tokens,
                    total_tokens=result.usage.total_tokens,
                    raw_provider_usage=result.usage.raw_provider_usage,
                ),
            )
        )
        if finished.status.value == "succeeded":
            self._successful_by_turn[finished.turn_number] = finished.id

    def successful_ai_call_id(self, turn_number: int) -> UUID | None:
        return self._successful_by_turn.get(turn_number)


__all__ = ["GenerationExecutionRecorder"]
