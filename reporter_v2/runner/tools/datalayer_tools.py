"""Datalayer tool adapters for the reporter v2 runner."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ai_gateway import ToolSpec
from datalayer.tools import SLEEPER_TOOLS, create_tool_handlers
from reporter_v2.runner.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from datalayer.sleeper_data import SleeperLeagueData


DATALAYER_TOOL_SPECS: list[ToolSpec] = ToolSpec.from_openai_tools(SLEEPER_TOOLS)


def register_datalayer_tools(
    registry: ToolRegistry,
    data: SleeperLeagueData,
) -> None:
    """Register all Sleeper datalayer tools in the runner registry."""
    handlers = create_tool_handlers(data)

    for spec in DATALAYER_TOOL_SPECS:
        handler = handlers[spec.name]
        registry.register(spec.name, _json_handler(handler), spec)


def _json_handler(handler: Callable[..., Any]) -> Callable[..., str]:
    def wrapped_handler(**kwargs: Any) -> str:
        return json.dumps(handler(**kwargs), default=str)

    return wrapped_handler
