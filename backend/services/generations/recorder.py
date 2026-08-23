"""Durable generation-scoped adapter for reporter execution events."""

from __future__ import annotations

from uuid import UUID

from backend.resources.reporting.ai_calls import (
    AICallManager,
    BeginAICall,
    FinishAICall,
    TokenUsage,
)
from backend.resources.reporting.generations import (
    GenerationManager,
    UpdateGenerationProgress,
)
from backend.resources.reporting.tool_calls import (
    BeginToolCall,
    FinishToolCall,
    ToolCallManager,
)
from backend.services.reporter.runner.recording import (
    GenerationProgress,
    ModelAttemptFinish,
    ModelAttemptStart,
    ToolExecutionFinish,
    ToolExecutionStart,
)


class GenerationExecutionRecorder:
    """Translate reporter execution events into durable reporting resources."""

    def __init__(
        self,
        generation_id: UUID,
        ai_call_manager: AICallManager,
        tool_call_manager: ToolCallManager,
        generation_manager: GenerationManager,
    ) -> None:
        self._generation_id = generation_id
        self._ai_call_manager = ai_call_manager
        self._tool_call_manager = tool_call_manager
        self._generation_manager = generation_manager
        self._successful_by_turn: dict[int, UUID] = {}
        self._last_progress: tuple[int, str] | None = None

    @property
    def generation_id(self) -> UUID:
        return self._generation_id

    def begin_model_attempt(self, attempt: ModelAttemptStart) -> UUID:
        started = self._ai_call_manager.begin_ai_call(
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
        finished = self._ai_call_manager.finish_ai_call(
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

    def begin_tool_execution(self, execution: ToolExecutionStart) -> UUID:
        ai_call_id = self.successful_ai_call_id(execution.turn_number)
        if ai_call_id is None:
            raise RuntimeError(
                "tool execution requires a successful AI call for "
                f"turn {execution.turn_number}"
            )
        started = self._tool_call_manager.begin_tool_call(
            BeginToolCall(
                generation_id=self._generation_id,
                ai_call_id=ai_call_id,
                tool_ordinal=execution.tool_ordinal,
                provider_tool_call_id=execution.provider_tool_call_id,
                tool_name=execution.tool_name,
                implementation_version=execution.implementation_version,
                arguments=execution.arguments,
            )
        )
        return started.id

    def finish_tool_execution(
        self,
        execution_id: UUID,
        result: ToolExecutionFinish,
    ) -> None:
        self._tool_call_manager.finish_tool_call(
            FinishToolCall(
                tool_call_id=execution_id,
                status=result.status,
                full_result_text=result.full_result_text,
                structured_result=result.structured_result,
                error_text=result.error_text,
                error=result.error,
            )
        )

    def update_progress(self, progress: GenerationProgress) -> None:
        checkpoint = (progress.current_turn, progress.current_stage)
        if checkpoint == self._last_progress:
            return
        self._generation_manager.update_progress(
            UpdateGenerationProgress(
                generation_id=self._generation_id,
                current_turn=progress.current_turn,
                current_stage=progress.current_stage,
            )
        )
        self._last_progress = checkpoint


__all__ = ["GenerationExecutionRecorder"]
