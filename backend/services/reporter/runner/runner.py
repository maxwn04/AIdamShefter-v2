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

from backend.services.reporter.runner.completion import (
    CompletionClient,
    CompletionFn,
    CompletionSettings,
)
from backend.services.reporter.runner.models import (
    ChatMessage,
    ToolCall,
    assistant_tool_call_message,
    extract_text,
    extract_tool_calls,
    tool_result_message,
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
from backend.services.reporter.runner.research_brief import ResearchBriefStore
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

__all__ = ["CompletionFn", "Runner", "RunnerRecordingError"]


_UNKNOWN_TOOL_IMPLEMENTATION_VERSION = "unregistered-v1"


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
        self.tool_context = ToolContext(
            artifacts=self.artifacts,
            procedures=self.procedures,
            log=self.log,
            brief=self.brief,
            artifact_recorder=self._artifact_recorder(recorder),
        )
        self.registry.set_context(self.tool_context)
        self._procedure_message_idx: int | None = None
        self._submitted = False

        if log_path is not None:
            self.log.start_streaming(log_path)

    @property
    def client(self) -> CompletionClient:
        return self._client

    async def run(self, system_prompt: str, user_message: str) -> ReporterOutput:
        messages: list[ChatMessage] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        turn = 0

        try:
            while turn < self.config.max_turns and not self._submitted:
                turn += 1
                self._record_progress(turn, self.procedures.active or "running")
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
                    if (
                        self.procedures.active is not None
                        and self.procedures.active != previous_stage
                    ):
                        self._record_progress(turn, self.procedures.active)
                    for call, result_content in zip(calls, results):
                        if call.name == "load_procedure":
                            self._append_procedure_message(messages, call, result_content)
                        else:
                            messages.append(tool_result_message(call, result_content))

                    continue

                text = extract_text(response)
                if text:
                    self.log.add_model_text(text, turn=turn)
                    messages.append({"role": "assistant", "content": text})
                    break

                break

            self.log.add_completion(
                {
                    "total_turns": turn,
                    "total_tool_calls": self.log.tool_call_count,
                    "submitted": self._submitted,
                },
                turn=turn,
            )
            return ReporterOutput(
                submitted_path=self.artifacts.submitted_path,
                artifacts=self.artifacts.list(),
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
                },
                run_log_entries=[
                    entry.model_dump(mode="json") for entry in self.log.entries
                ],
            )
        finally:
            self.log.stop_streaming()

    async def _execute_tool_batch(
        self,
        calls: list[ToolCall],
        turn: int,
    ) -> list[str]:
        executed = await asyncio.gather(
            *[
                self._execute_tool(call, turn, ordinal)
                for ordinal, call in enumerate(calls)
            ]
        )
        return list(executed)

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
            result: Any = {"error": message}
            result_content = self._as_tool_result_content(result)
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
                    full_result_text=result_content,
                    structured_result=cast(dict[str, JsonValue], result),
                    error_text=message,
                    error=error,
                ),
            )
            return result_content

        artifact_recording_error: ArtifactRecordingError | None = None
        try:
            with self.tool_context.bind_tool_execution(execution_id):
                result = handler(**call.arguments)
                if asyncio.iscoroutine(result):
                    result = await result
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
            result = {"error": error_text}
            status = "failed"
        except Exception as exc:
            error = sanitize_provider_error(exc)
            error_text = str(error.get("message") or type(exc).__name__)
            result = {"error": error_text}
            status = "failed"
        else:
            error = None
            error_text = None
            status = "succeeded"

        duration_ms = self._duration_ms(start)
        result_content = self._as_tool_result_content(result)
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
                full_result_text=result_content,
                structured_result=self._structured_result(result_content),
                error_text=error_text,
                error=error,
            ),
        )

        if artifact_recording_error is not None:
            raise RunnerRecordingError(
                "Could not record durable artifact mutation"
            ) from artifact_recording_error

        if call.name == "submit_artifact" and self._is_successful_submit(result_content):
            self._submitted = True

        return result_content

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
        if isinstance(result, str):
            return result
        return json.dumps(result, default=str)

    @staticmethod
    def _is_successful_submit(result: str) -> bool:
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            return False
        return isinstance(data, dict) and data.get("ok") is True

    @staticmethod
    def _structured_result(
        result: str,
    ) -> dict[str, JsonValue] | list[JsonValue] | None:
        try:
            parsed = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            return None
        if isinstance(parsed, dict):
            return cast(dict[str, JsonValue], parsed)
        if isinstance(parsed, list):
            return cast(list[JsonValue], parsed)
        return None

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
