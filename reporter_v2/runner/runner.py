"""Core v2 runner loop.

The Runner is the agent engine: it owns the message loop, tool execution,
procedure-message compaction, and ArticleOutput assembly. It does not know
about Sleeper, ReportConfig, memory, or which tools are registered — callers
(typically generate_article) wire those in.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from reporter_v2.runner.completion import CompletionClient, CompletionFn, CompletionSettings
from reporter_v2.runner.models import (
    ChatMessage,
    ToolCall,
    assistant_tool_call_message,
    extract_text,
    extract_tool_calls,
    tool_result_message,
)
from reporter_v2.runner.run_log import RunLog
from reporter_v2.runner.schemas import ArticleOutput
from reporter_v2.runner.state import (
    ArtifactStore,
    ProcedureHistoryMode,
    ProcedureState,
    RunnerConfig,
)
from reporter_v2.runner.tools.context import ToolContext
from reporter_v2.runner.tools.registry import ToolRegistry

__all__ = ["CompletionFn", "Runner"]


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
        self.config = config or RunnerConfig()
        self.artifacts = artifacts or ArtifactStore()
        self.procedures = ProcedureState()
        self.log = RunLog()
        self.tool_context = ToolContext(
            artifacts=self.artifacts,
            procedures=self.procedures,
            log=self.log,
        )
        self.registry.set_context(self.tool_context)
        self._procedure_message_idx: int | None = None
        self._submitted = False

        if log_path is not None:
            self.log.start_streaming(log_path)

    @property
    def client(self) -> CompletionClient:
        return self._client

    async def run(self, system_prompt: str, user_message: str) -> ArticleOutput:
        messages: list[ChatMessage] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        turn = 0

        try:
            while turn < self.config.max_turns and not self._submitted:
                turn += 1
                response = await self._client.complete(
                    messages=list(messages),
                    tools=self.registry.tool_specs,
                )

                calls = extract_tool_calls(response)
                if calls:
                    self.registry.set_turn(turn)
                    messages.append(assistant_tool_call_message(calls, response))
                    results = await self._execute_tool_batch(calls, turn)
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
            return ArticleOutput(
                article=self.artifacts.article.to_markdown(),
                brief=self.artifacts.brief,
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
            *[self._execute_tool(call, turn) for call in calls]
        )
        return list(executed)

    async def _execute_tool(self, call: ToolCall, turn: int) -> str:
        handler = self.registry.get_handler(call.name)
        if handler is None:
            result: Any = {"error": f"Unknown tool: {call.name}"}
            result_content = self._as_tool_result_content(result)
            self.log.add_tool_call(call.name, call.arguments, result_content, 0, turn=turn)
            return result_content

        start = time.time()
        try:
            result = handler(**call.arguments)
            if asyncio.iscoroutine(result):
                result = await result
        except Exception as exc:
            result = {"error": str(exc)}

        duration_ms = int((time.time() - start) * 1000)
        result_content = self._as_tool_result_content(result)
        self.log.add_tool_call(
            call.name,
            call.arguments,
            self._summarize_result(result_content),
            duration_ms,
            turn=turn,
        )

        if call.name == "submit_article" and self._is_successful_submit(result_content):
            self._submitted = True

        return result_content

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
