"""Tool registry for the v2 runner."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.services.reporter.runner.models import ToolDef
from backend.services.reporter.runner.tools.context import ToolContext


class ToolRegistry:
    """Maps tool names to handlers and exposes gateway tool specs."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., Any]] = {}
        self._specs: dict[str, ToolDef] = {}
        self._implementation_versions: dict[str, str] = {}
        self._context: ToolContext | None = None

    def set_context(self, context: ToolContext) -> None:
        self._context = context

    @property
    def context(self) -> ToolContext | None:
        return self._context

    def register(
        self,
        name: str,
        handler: Callable[..., Any],
        spec: ToolDef,
        implementation_version: str,
    ) -> None:
        if (
            not implementation_version
            or implementation_version.strip() != implementation_version
        ):
            raise ValueError("tool implementation version must be non-blank and trimmed")
        self._handlers[name] = handler
        self._specs[name] = spec
        self._implementation_versions[name] = implementation_version

    def register_context_tool(
        self,
        name: str,
        handler: Callable[..., Any],
        spec: ToolDef,
        implementation_version: str,
    ) -> None:
        def bound_handler(**kwargs: Any) -> Any:
            if self._context is None:
                raise RuntimeError("ToolRegistry context has not been set.")
            return handler(self._context, **kwargs)

        self.register(name, bound_handler, spec, implementation_version)

    def get_handler(self, name: str) -> Callable[..., Any] | None:
        return self._handlers.get(name)

    def get_implementation_version(self, name: str) -> str | None:
        return self._implementation_versions.get(name)

    def set_turn(self, turn: int) -> None:
        if self._context is not None:
            self._context.turn = turn

    @property
    def tool_specs(self) -> list[ToolDef]:
        return list(self._specs.values())

    @property
    def tool_names(self) -> list[str]:
        return list(self._handlers.keys())

    @property
    def tool_implementation_versions(self) -> list[tuple[str, str]]:
        return list(self._implementation_versions.items())
