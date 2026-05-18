"""Core v2 runner loop."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from ai_gateway import (
    AiGateway,
    AiRequest,
    ChatMessage,
    ToolCall,
    ToolResultMessage,
)
from reporter_v2.runner.run_log import RunLog
from reporter_v2.runner.schemas import ArticleOutput
from reporter_v2.runner.state import ArtifactStore, ProcedureState, RunnerConfig
from reporter_v2.runner.tools.context import ToolContext
from reporter_v2.runner.tools.registry import ToolRegistry


class Runner:
    """Single-loop runner that drives research, drafting, and verification."""

    def __init__(
        self,
        gateway: AiGateway,
        registry: ToolRegistry,
        *,
        config: RunnerConfig | None = None,
        log_path: Path | None = None,
    ) -> None:
        self.gateway = gateway
        self.registry = registry
        self.config = config or RunnerConfig()
        self.artifacts = ArtifactStore()
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

    async def run(self, system_prompt: str, user_message: str) -> ArticleOutput:
        messages: list[ChatMessage | ToolResultMessage] = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_message),
        ]
        turn = 0
        previous_response_id: str | None = None

        try:
            while turn < self.config.max_turns and not self._submitted:
                turn += 1
                provider_context = {}
                if previous_response_id is not None:
                    provider_context["previous_response_id"] = previous_response_id
                request = AiRequest(
                    messages=list(messages),
                    tools=self.registry.tool_specs,
                    model=self.config.model,
                    provider_context=provider_context,
                )
                response = await self.gateway.get_response(request)
                response_id = response.provider_metadata.get("response_id")
                if response_id is not None:
                    previous_response_id = str(response_id)

                if response.tool_calls:
                    self.registry.set_turn(turn)
                    results = await self._execute_tool_batch(response.tool_calls, turn)
                    for call, result_content in zip(response.tool_calls, results):
                        if call.name == "load_procedure":
                            self._replace_procedure_message(messages, call, result_content)
                        else:
                            messages.append(ToolResultMessage.from_call(call, result_content))

                    self._check_guardrails(messages, turn)
                    continue

                if response.text:
                    self.log.add_model_text(response.text, turn=turn)
                    messages.append(ChatMessage(role="assistant", content=response.text))
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
            )
        finally:
            self.log.stop_streaming()

    async def _execute_tool_batch(
        self,
        calls: list[ToolCall],
        turn: int,
    ) -> list[str]:
        results: list[str | None] = [None] * len(calls)
        scheduled: list[tuple[int, ToolCall]] = []
        remaining_tool_slots = max(
            self.config.hard_tool_limit - self.log.tool_call_count,
            0,
        )

        for index, call in enumerate(calls):
            if call.name == "submit_article" or remaining_tool_slots > 0:
                scheduled.append((index, call))
                if call.name != "submit_article":
                    remaining_tool_slots -= 1
            else:
                results[index] = self._hard_limit_tool_result(turn)

        executed = await asyncio.gather(
            *[self._execute_tool(call, turn) for _, call in scheduled]
        )
        for (index, _), result in zip(scheduled, executed):
            results[index] = result

        return [result or "" for result in results]

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

    def _hard_limit_tool_result(self, turn: int) -> str:
        self.log.add_guardrail(
            "hard_tool_limit_blocked",
            self.log.tool_call_count,
            self.config.hard_tool_limit,
            turn=turn,
        )
        return self._as_tool_result_content(
            {
                "ok": False,
                "error": (
                    "Hard tool limit reached. Only submit_article may be called."
                ),
            }
        )

    def _replace_procedure_message(
        self,
        messages: list[ChatMessage | ToolResultMessage],
        call: ToolCall,
        content: str,
    ) -> None:
        """Remove the previous procedure message and append the new one."""
        if self._procedure_message_idx is not None:
            messages.pop(self._procedure_message_idx)

        messages.append(ToolResultMessage.from_call(call, content))
        self._procedure_message_idx = len(messages) - 1

    def _check_guardrails(
        self,
        messages: list[ChatMessage | ToolResultMessage],
        turn: int,
    ) -> None:
        tool_count = self.log.tool_call_count
        if tool_count >= self.config.hard_tool_limit:
            self.log.add_guardrail(
                "hard_tool_limit",
                tool_count,
                self.config.hard_tool_limit,
                turn=turn,
            )
            messages.append(
                ChatMessage(
                    role="system",
                    content=(
                        "HARD LIMIT REACHED. You must call submit_article() now. "
                        "Do not make any more research or data tool calls."
                    ),
                )
            )
            return

        if tool_count >= self.config.soft_tool_limit:
            self.log.add_guardrail(
                "soft_tool_limit",
                tool_count,
                self.config.soft_tool_limit,
                turn=turn,
            )
            messages.append(
                ChatMessage(
                    role="system",
                    content=(
                        f"You have used {tool_count} tool calls. Start wrapping up: "
                        "finalize your brief and move to drafting."
                    ),
                )
            )

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
