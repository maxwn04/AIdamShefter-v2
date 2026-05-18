# Phase 6: The Runner Loop

**Goal:** The core `run()` function -- the while loop that calls the gateway,
dispatches tools, manages messages, and handles guardrails.

**Files to create:**
- `reporter_v2/runner/runner.py`
- `reporter_v2/runner/tools/registry.py`
- `reporter_v2/tests/test_runner.py`

**Dependencies:** Phases 1-5

---

## `reporter_v2/runner/tools/registry.py` -- ToolRegistry

The registry maps tool names to callables and provides `ToolSpec` objects for the
gateway request.

```python
from __future__ import annotations

from typing import Any, Callable

from ai_gateway import ToolSpec


class ToolRegistry:
    """Maps tool names to handler functions and provides ToolSpecs for the gateway."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., str]] = {}
        self._specs: dict[str, ToolSpec] = {}

    def register(
        self, name: str, handler: Callable[..., str], spec: ToolSpec,
    ) -> None:
        self._handlers[name] = handler
        self._specs[name] = spec

    def get_handler(self, name: str) -> Callable[..., str] | None:
        return self._handlers.get(name)

    @property
    def tool_specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    @property
    def tool_names(self) -> list[str]:
        return list(self._handlers.keys())
```

## `reporter_v2/runner/runner.py` -- The Runner

```python
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from ai_gateway import (
    AiGateway, AiRequest, AiResponse, ChatMessage,
    ToolCall, ToolResultMessage,
)
from reporter_v2.runner.run_log import RunLog
from reporter_v2.runner.schemas import ArticleOutput
from reporter_v2.runner.state import ArtifactStore, ProcedureState, RunnerConfig
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
        self._procedure_message_idx: int | None = None
        self._submitted = False

        if log_path:
            self.log.start_streaming(log_path)

    async def run(
        self, system_prompt: str, user_message: str,
    ) -> ArticleOutput:
        messages: list[ChatMessage | ToolResultMessage] = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_message),
        ]
        turn = 0

        try:
            while turn < self.config.max_turns and not self._submitted:
                turn += 1
                request = AiRequest(
                    messages=list(messages),
                    tools=self.registry.tool_specs,
                    model=self.config.model,
                )
                response = await self.gateway.get_response(request)

                if response.tool_calls:
                    results = await asyncio.gather(*[
                        self._execute_tool(tc, turn)
                        for tc in response.tool_calls
                    ])
                    for call, result_content in zip(response.tool_calls, results):
                        if call.name == "load_procedure":
                            self._replace_procedure_message(
                                messages, call, result_content
                            )
                        else:
                            messages.append(
                                ToolResultMessage.from_call(call, result_content)
                            )

                    self._check_guardrails(messages, turn)

                elif response.text:
                    self.log.add_model_text(response.text, turn=turn)
                    messages.append(
                        ChatMessage(role="assistant", content=response.text)
                    )
                else:
                    break

            return ArticleOutput(
                article=self.artifacts.article.to_markdown(),
                brief=self.artifacts.brief,
                run_log_summary={
                    "session_id": self.log.session_id,
                    "total_tool_calls": self.log.tool_call_count,
                    "total_turns": turn,
                    "procedures_loaded": [
                        p.to_procedure for p in self.log.procedure_history
                    ],
                },
            )
        finally:
            self.log.stop_streaming()

    async def _execute_tool(self, call: ToolCall, turn: int) -> str:
        handler = self.registry.get_handler(call.name)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {call.name}"})

        start = time.time()
        try:
            result = handler(**call.arguments)
            if asyncio.iscoroutine(result):
                result = await result
        except Exception as e:
            result = json.dumps({"error": str(e)})

        duration_ms = int((time.time() - start) * 1000)
        summary = self._summarize_result(call.name, result)
        self.log.add_tool_call(
            call.name, call.arguments, summary, duration_ms, turn=turn,
        )

        if call.name == "submit_article":
            self._submitted = True

        return result if isinstance(result, str) else json.dumps(result)

    def _replace_procedure_message(
        self, messages: list, call: ToolCall, content: str,
    ) -> None:
        """Remove previous procedure message, append new one."""
        if self._procedure_message_idx is not None:
            messages.pop(self._procedure_message_idx)
        msg = ToolResultMessage.from_call(call, content)
        messages.append(msg)
        self._procedure_message_idx = len(messages) - 1

    def _check_guardrails(self, messages: list, turn: int) -> None:
        tc = self.log.tool_call_count
        if tc >= self.config.hard_tool_limit:
            self.log.add_guardrail(
                "hard_tool_limit", tc, self.config.hard_tool_limit, turn=turn
            )
            messages.append(ChatMessage(
                role="system",
                content=(
                    "HARD LIMIT REACHED. You must call submit_article() now. "
                    "Do not make any more research or data tool calls."
                ),
            ))
        elif tc >= self.config.soft_tool_limit:
            self.log.add_guardrail(
                "soft_tool_limit", tc, self.config.soft_tool_limit, turn=turn
            )
            messages.append(ChatMessage(
                role="system",
                content=(
                    f"You have used {tc} tool calls. Start wrapping up: "
                    "finalize your brief and move to drafting."
                ),
            ))

    @staticmethod
    def _summarize_result(tool_name: str, result: str) -> str:
        if len(result) <= 100:
            return result
        try:
            data = json.loads(result)
            if isinstance(data, dict):
                if "error" in data:
                    return f"error: {data['error'][:80]}"
                return f"dict with {len(data)} keys"
            if isinstance(data, list):
                return f"{len(data)} items"
        except (json.JSONDecodeError, TypeError):
            pass
        return result[:80] + "..."
```

## How Tool Functions Are Registered

The `Runner` doesn't directly know about `brief_tools` or `article_tools`. A
setup function creates the registry with all tools bound to the runner's state.
Tool functions receive `ToolContext`; the registry stores closures that bind it.

The key insight: tool functions take `(ctx: ToolContext, **kwargs)`. The registry
stores a wrapper that binds the context at registration time. The `turn` field
on `ToolContext` is updated by the runner before each tool dispatch batch.

## Tests

- `test_runner_simple_text_response` -- gateway returns text only, runner completes
- `test_runner_tool_call_dispatch` -- gateway returns a tool call, verify handler called
- `test_runner_submit_article_breaks_loop` -- verify loop stops on submit_article
- `test_runner_soft_guardrail` -- verify system message injected at soft limit
- `test_runner_hard_guardrail` -- verify system message injected at hard limit
- `test_runner_procedure_replacement` -- verify old procedure message removed from messages
- `test_runner_max_turns` -- verify loop stops at max_turns

All tests use a fake `AiGateway` that returns canned `AiResponse` objects. No
real API calls.
