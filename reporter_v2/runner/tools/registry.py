"""Tool registry for the v2 runner."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ai_gateway import ToolSpec
from reporter_v2.runner.tools.context import ToolContext


class ToolRegistry:
    """Maps tool names to handlers and exposes gateway tool specs."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., Any]] = {}
        self._specs: dict[str, ToolSpec] = {}
        self._context: ToolContext | None = None

    def set_context(self, context: ToolContext) -> None:
        self._context = context

    def register(
        self,
        name: str,
        handler: Callable[..., Any],
        spec: ToolSpec,
    ) -> None:
        self._handlers[name] = handler
        self._specs[name] = spec

    def register_context_tool(
        self,
        name: str,
        handler: Callable[..., Any],
        spec: ToolSpec,
    ) -> None:
        def bound_handler(**kwargs: Any) -> Any:
            if self._context is None:
                raise RuntimeError("ToolRegistry context has not been set.")
            return handler(self._context, **kwargs)

        self.register(name, bound_handler, spec)

    def get_handler(self, name: str) -> Callable[..., Any] | None:
        return self._handlers.get(name)

    def set_turn(self, turn: int) -> None:
        if self._context is not None:
            self._context.turn = turn

    @property
    def tool_specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    @property
    def tool_names(self) -> list[str]:
        return list(self._handlers.keys())
