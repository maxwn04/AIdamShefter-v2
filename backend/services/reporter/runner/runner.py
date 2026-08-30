"""Core v2 runner loop.

The Runner is the agent engine: it owns the message loop, tool execution,
procedure-message compaction, and ReporterOutput assembly. It does not know
about Sleeper, ReportConfig, memory, or which tools are registered — callers
(typically generate_article) wire those in.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from pydantic import JsonValue

from backend.services.reporter.runner.artifact_recording import TurnArtifactRecorder
from backend.services.reporter.runner.completion import (
    CompletionClient,
    CompletionFn,
    CompletionSettings,
)
from backend.services.reporter.runner.models import (
    ChatMessage,
    ToolCall,
    ToolExecutionResult,
    assistant_tool_call_message,
    extract_text,
    extract_tool_calls,
    serialize_model_value,
    tool_result_message,
)
from backend.services.reporter.runner.memory_closeout import (
    MEMORY_CLOSEOUT_TURN_ALLOWANCE,
    MemoryCloseoutIncompleteError,
    MemoryCloseoutState,
)
from backend.services.reporter.runner.provider_telemetry import sanitize_provider_error
from backend.services.reporter.runner.recording import (
    ArtifactRecorder,
    ArtifactRecordingError,
    GenerationProgress,
    RunnerRecorder,
    ToolExecutionFinish,
    ToolExecutionStart,
)
from backend.services.reporter.runner.research_brief import (
    RESEARCH_BRIEF_PATH,
    ResearchBriefStore,
)
from backend.services.reporter.runner.run_log import RunLog
from backend.services.reporter.runner.schemas import ReporterOutput
from backend.services.reporter.runner.state import (
    ArtifactStore,
    ProcedureHistoryMode,
    ProcedureState,
    RunnerConfig,
)
from backend.services.reporter.runner.tools.context import ToolContext
from backend.services.reporter.runner.tools.registry import ToolRegistry

__all__ = [
    "CompletionFn",
    "MemoryCloseoutIncompleteError",
    "Runner",
    "RunnerRecordingError",
]


_UNKNOWN_TOOL_IMPLEMENTATION_VERSION = "unregistered-v1"
_MEMORY_CLOSEOUT_TOOL_NAME = "complete_memory_review"


class RunnerRecordingError(RuntimeError):
    """Durable runner recording failed, so execution cannot continue."""


class Runner:
    """Single-loop runner that drives research, drafting, and verification."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        client: CompletionClient | None = None,
        complete: CompletionFn | None = None,
        config: RunnerConfig | None = None,
        log_path: Path | None = None,
        artifacts: ArtifactStore | None = None,
        brief: ResearchBriefStore | None = None,
        recorder: RunnerRecorder | None = None,
        memory_closeout: MemoryCloseoutState | None = None,
    ) -> None:
        if client is not None and complete is not None:
            raise ValueError("Pass client= or complete=, not both.")
        if client is not None:
            self._client = client
        elif complete is not None:
            # Test convenience: wrap a raw completion fn without litellm.
            self._client = CompletionClient(complete, CompletionSettings())
        else:
            raise TypeError("Runner requires client= (or complete= for tests).")

        self.registry = registry
        self._recorder = recorder
        self.config = config or RunnerConfig()
        self.artifacts = artifacts or ArtifactStore()
        self.brief = brief or ResearchBriefStore()
        self.procedures = ProcedureState()
        self.log = RunLog()
        artifact_recorder = self._artifact_recorder(recorder)
        self._turn_artifacts = (
            TurnArtifactRecorder(artifact_recorder)
            if artifact_recorder is not None
            else None
        )
        self.tool_context = ToolContext(
            artifacts=self.artifacts,
            procedures=self.procedures,
            log=self.log,
            brief=self.brief,
            artifact_recorder=self._turn_artifacts,
            memory_closeout=memory_closeout,
        )
        self.registry.set_context(self.tool_context)
        self._procedure_message_idx: int | None = None
        self._submitted = False
        self._memory_closeout = memory_closeout

        if log_path is not None:
            self.log.start_streaming(log_path)

    @property
    def client(self) -> CompletionClient:
        return self._client

    async def run(
        self,
        system_prompt: str,
        user_message: str,
        *,
        initial_context: tuple[str, ...] = (),
    ) -> ReporterOutput:
        messages: list[ChatMessage] = [
            {"role": "system", "content": system_prompt},
            *(
                {"role": "user", "content": content}
                for content in initial_context
            ),
            {"role": "user", "content": user_message},
        ]
        turn = 0

        try:
            while self._can_start_turn(turn):
                turn += 1
                if self._memory_closeout is not None:
                    self._memory_closeout.begin_turn()
                stage = (
                    "memory_closeout"
                    if self._memory_closeout is not None
                    and self._memory_closeout.article_submitted
                    else self.procedures.active or "running"
                )
                self._record_progress(turn, stage)
                response = await self._client.complete(
                    turn_number=turn,
                    messages=list(messages),
                    tools=self.registry.tool_specs,
                )

                calls = extract_tool_calls(response)
                if calls:
                    self.registry.set_turn(turn)
                    messages.append(assistant_tool_call_message(calls, response))
                    previous_stage = self.procedures.active
                    results = await self._execute_tool_batch(calls, turn)
                    self._flush_artifact_turn(turn)
                    if any(
                        call.name == "submit_artifact"
                        and self._is_successful_submit(result)
                        for call, result in zip(calls, results)
                    ):
                        self._activate_submission(turn)
                    if (
                        self.procedures.active is not None
                        and self.procedures.active != previous_stage
                    ):
                        self._record_progress(turn, self.procedures.active)
                    for call, result_content in zip(calls, results):
                        if call.name == "load_procedure":
                            self._append_procedure_message(
                                messages,
                                call,
                                result_content,
                            )
                        else:
                            messages.append(tool_result_message(call, result_content))

                    continue

                text = extract_text(response)
                if text:
                    self.log.add_model_text(text, turn=turn)
                    messages.append({"role": "assistant", "content": text})
                    if self._closeout_is_active():
                        continue
                    break

                if self._closeout_is_active():
                    continue
                break

            self.log.add_completion(
                {
                    "total_turns": turn,
                    "total_tool_calls": self.log.tool_call_count,
                    "submitted": self._submitted,
                },
                turn=turn,
            )
            artifact_snapshots = self.artifacts.list()
            if self._turn_artifacts is not None:
                artifact_snapshots = self._turn_artifacts.durable_snapshots(
                    artifact_snapshots
                )
            return ReporterOutput(
                submitted_path=self.artifacts.submitted_path,
                artifacts=artifact_snapshots,
                research_brief=self.brief.brief,
                run_log_summary={
                    "session_id": self.log.session_id,
                    "total_tool_calls": self.log.tool_call_count,
                    "total_turns": turn,
                    "procedures_loaded": [
                        procedure.to_procedure
                        for procedure in self.log.procedure_history
                    ],
                    "submitted": self._submitted,
                    "memory_closeout": self._closeout_summary(),
                    "brief": self._build_brief_summary(),
                },
                run_log_entries=[
                    entry.model_dump(mode="json") for entry in self.log.entries
                ],
            )
        finally:
            self.log.stop_streaming()

    def _build_brief_summary(self) -> dict[str, Any]:
        brief = self.brief.brief
        readiness = brief.readiness().model_dump(mode="json")
        projection = self.artifacts.artifacts.get(RESEARCH_BRIEF_PATH)
        draft_path = self.artifacts.submitted_path
        first_draft_turn = self.log.first_artifact_write_turn(
            operations=frozenset({"create_artifact", "edit_artifact"}),
            artifact=draft_path,
        )
        if first_draft_turn is None and draft_path is None:
            first_draft_turn = self.log.first_artifact_write_turn(
                operations=frozenset({"create_artifact", "edit_artifact"}),
                excluded_artifacts=frozenset({RESEARCH_BRIEF_PATH}),
            )
        return {
            "revision": brief.revision,
            "projection_revision": (
                projection.current.revision if projection is not None else None
            ),
            "fact_count": readiness["fact_count"],
            "callback_count": readiness["callback_count"],
            "storyline_count": readiness["storyline_count"],
            "outline_section_count": readiness["outline_section_count"],
            "stale_callback_ids": readiness["stale_callback_ids"],
            "stale_storyline_ids": readiness["stale_storyline_ids"],
            "outline_stale": readiness["outline_stale"],
            "readiness_warnings": readiness["warnings"],
            "first_fact_turn": self.log.first_artifact_write_turn(
                operations=frozenset({"save_fact"}),
                artifact=RESEARCH_BRIEF_PATH,
            ),
            "first_storyline_turn": self.log.first_artifact_write_turn(
                operations=frozenset({"save_storyline"}),
                artifact=RESEARCH_BRIEF_PATH,
            ),
            "first_draft_turn": first_draft_turn,
            "submission_turn": self.log.first_artifact_write_turn(
                operations=frozenset({"submit_artifact"}),
                artifact=draft_path,
            ),
        }

    async def _execute_tool_batch(
        self,
        calls: list[ToolCall],
        turn: int,
    ) -> list[str]:
        results: list[str | None] = [None] * len(calls)
        regular = [
            (ordinal, call)
            for ordinal, call in enumerate(calls)
            if call.name != _MEMORY_CLOSEOUT_TOOL_NAME
        ]
        if regular:
            executed = await asyncio.gather(
                *[
                    self._execute_tool(call, turn, ordinal)
                    for ordinal, call in regular
                ]
            )
            for (ordinal, _), result in zip(regular, executed):
                results[ordinal] = result

        for ordinal, call in enumerate(calls):
            if call.name == _MEMORY_CLOSEOUT_TOOL_NAME:
                results[ordinal] = await self._execute_tool(call, turn, ordinal)
        return [cast(str, result) for result in results]

    async def _execute_tool(
        self,
        call: ToolCall,
        turn: int,
        ordinal: int,
    ) -> str:
        handler = self.registry.get_handler(call.name)
        implementation_version = (
            self.registry.get_implementation_version(call.name)
            or _UNKNOWN_TOOL_IMPLEMENTATION_VERSION
        )
        execution_id = self._begin_tool_execution(
            ToolExecutionStart(
                turn_number=turn,
                tool_ordinal=ordinal,
                provider_tool_call_id=call.id or None,
                tool_name=call.name,
                implementation_version=implementation_version,
                arguments=cast(dict[str, JsonValue], call.arguments),
            )
        )
        start = time.time()
        if handler is None:
            message = f"Unknown tool: {call.name}"
            error: dict[str, JsonValue] = {
                "type": "UnknownToolError",
                "message": message,
            }
            execution_result = ToolExecutionResult(result={"error": message})
            result_content = self._as_tool_result_content(execution_result.result)
            duration_ms = self._duration_ms(start)
            self.log.add_tool_call(
                call.name,
                call.arguments,
                result_content,
                duration_ms,
                turn=turn,
            )
            self._finish_tool_execution(
                execution_id,
                ToolExecutionFinish(
                    status="failed",
                    result=execution_result.result,
                    result_text=result_content,
                    metadata=execution_result.metadata,
                    error_text=message,
                    error=error,
                ),
            )
            return result_content

        artifact_recording_error: ArtifactRecordingError | None = None
        try:
            with self.tool_context.bind_tool_execution(execution_id):
                handler_result = handler(**call.arguments)
                if asyncio.iscoroutine(handler_result):
                    handler_result = await handler_result
        except asyncio.CancelledError:
            self._finish_tool_execution(
                execution_id,
                ToolExecutionFinish(status="cancelled"),
            )
            raise
        except ArtifactRecordingError as exc:
            artifact_recording_error = exc
            error = sanitize_provider_error(exc)
            error_text = str(error.get("message") or type(exc).__name__)
            handler_result = {"error": error_text}
            status = "failed"
        except Exception as exc:
            error = sanitize_provider_error(exc)
            error_text = str(error.get("message") or type(exc).__name__)
            handler_result = {"error": error_text}
            status = "failed"
        else:
            error = None
            error_text = None
            status = "succeeded"

        duration_ms = self._duration_ms(start)
        execution_result = self._normalize_tool_result(handler_result)
        result_content = self._as_tool_result_content(execution_result.result)
        self.log.add_tool_call(
            call.name,
            call.arguments,
            self._summarize_result(result_content),
            duration_ms,
            turn=turn,
        )
        self._finish_tool_execution(
            execution_id,
            ToolExecutionFinish(
                status=status,
                result=execution_result.result,
                result_text=result_content,
                metadata=execution_result.metadata,
                error_text=error_text,
                error=error,
            ),
        )

        if artifact_recording_error is not None:
            raise RunnerRecordingError(
                "Could not record durable artifact mutation"
            ) from artifact_recording_error

        return result_content

    def _can_start_turn(self, turn: int) -> bool:
        state = self._memory_closeout
        if state is not None:
            if state.memory_review_completed:
                return False
            if state.article_submitted:
                if state.closeout_turns_used >= MEMORY_CLOSEOUT_TURN_ALLOWANCE:
                    state.mark_exhausted()
                    self.log.add_memory_closeout(
                        "limit_exhausted",
                        turn=turn,
                        turns_used=state.closeout_turns_used,
                        turn_allowance=MEMORY_CLOSEOUT_TURN_ALLOWANCE,
                    )
                    self._record_progress(turn, "memory_closeout_exhausted")
                    raise MemoryCloseoutIncompleteError(
                        "Memory review was not completed within the six-turn "
                        "closeout allowance."
                    )
                return True
        return turn < self.config.max_turns and not self._submitted

    def _activate_submission(self, turn: int) -> None:
        self._submitted = True
        state = self._memory_closeout
        if state is None or state.article_submitted:
            return
        state.activate(turn=turn)
        self.log.add_memory_closeout(
            "closeout_activated",
            turn=turn,
            turn_allowance=MEMORY_CLOSEOUT_TURN_ALLOWANCE,
            memory_writes_enabled=state.memory_writes_enabled,
        )
        self._record_progress(turn, "memory_closeout")

    def _closeout_is_active(self) -> bool:
        return self._memory_closeout is not None and self._memory_closeout.active

    def _closeout_summary(self) -> dict[str, Any]:
        if self._memory_closeout is None:
            return {"enabled": False, "status": "not_applicable"}
        return self._memory_closeout.summary()

    def _begin_tool_execution(self, execution: ToolExecutionStart) -> UUID | None:
        if self._recorder is None:
            return None
        try:
            return self._recorder.begin_tool_execution(execution)
        except Exception as exc:
            raise RunnerRecordingError(
                f"Could not begin durable tool execution for {execution.tool_name}"
            ) from exc

    def _finish_tool_execution(
        self,
        execution_id: UUID | None,
        result: ToolExecutionFinish,
    ) -> None:
        if self._recorder is None:
            return
        if execution_id is None:
            raise RunnerRecordingError("Durable tool execution ID is missing")
        try:
            self._recorder.finish_tool_execution(execution_id, result)
        except Exception as exc:
            raise RunnerRecordingError(
                "Could not finish durable tool execution"
            ) from exc

    def _record_progress(self, turn: int, stage: str) -> None:
        if self._recorder is None:
            return
        try:
            self._recorder.update_progress(
                GenerationProgress(current_turn=turn, current_stage=stage)
            )
        except Exception as exc:
            raise RunnerRecordingError(
                f"Could not record generation progress for turn {turn}"
            ) from exc

    def _flush_artifact_turn(self, turn: int) -> None:
        if self._turn_artifacts is None:
            return
        try:
            self._turn_artifacts.flush_turn()
        except Exception as exc:
            raise RunnerRecordingError(
                f"Could not record durable artifact versions for turn {turn}"
            ) from exc

    @staticmethod
    def _artifact_recorder(
        recorder: RunnerRecorder | None,
    ) -> ArtifactRecorder | None:
        if recorder is None:
            return None
        method = getattr(recorder, "record_artifact_mutation", None)
        return cast(ArtifactRecorder, recorder) if callable(method) else None

    def _append_procedure_message(
        self,
        messages: list[ChatMessage],
        call: ToolCall,
        content: str,
    ) -> None:
        """Append procedure output, compacting prior output when configured."""
        if (
            self.config.procedure_history_mode == ProcedureHistoryMode.REPLACE
            and self._procedure_message_idx is not None
        ):
            messages[self._procedure_message_idx]["content"] = "[procedure replaced]"

        messages.append(tool_result_message(call, content))
        if self.config.procedure_history_mode == ProcedureHistoryMode.REPLACE:
            self._procedure_message_idx = len(messages) - 1

    @staticmethod
    def _as_tool_result_content(result: Any) -> str:
        return serialize_model_value(result)

    @staticmethod
    def _is_successful_submit(result: str) -> bool:
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            return False
        return isinstance(data, dict) and data.get("ok") is True

    @staticmethod
    def _normalize_tool_result(result: Any) -> ToolExecutionResult:
        if isinstance(result, ToolExecutionResult):
            return result
        return ToolExecutionResult(result=cast(JsonValue, result))

    @staticmethod
    def _duration_ms(start: float) -> int:
        return max(0, int((time.time() - start) * 1000))

    @staticmethod
    def _summarize_result(result: str) -> str:
        if len(result) <= 100:
            return result

        try:
            data = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            return result[:80] + "..."

        if isinstance(data, dict):
            if "error" in data:
                return f"error: {str(data['error'])[:80]}"
            return f"dict with {len(data)} keys"
        if isinstance(data, list):
            return f"{len(data)} items"
        return result[:80] + "..."
