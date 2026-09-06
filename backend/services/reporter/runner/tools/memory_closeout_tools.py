"""Terminal tool for mandatory same-agent memory review."""

from __future__ import annotations

from typing import Any

from backend.services.reporter.runner.models import ToolDef
from backend.services.reporter.runner.tools.context import ToolContext
from backend.services.reporter.runner.tools.registry import ToolRegistry


MEMORY_CLOSEOUT_TOOL_IMPLEMENTATION_VERSION = "2"

MEMORY_CLOSEOUT_TOOL_SPECS: list[ToolDef] = [
    {
        "type": "function",
        "function": {
            "name": "complete_memory_review",
            "description": (
                "Complete the mandatory post-submission memory review after saving "
                "durable continuity or deliberately choosing a no-op."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    }
]


def register_memory_closeout_tools(registry: ToolRegistry) -> None:
    registry.register_context_tool(
        "complete_memory_review",
        complete_memory_review,
        MEMORY_CLOSEOUT_TOOL_SPECS[0],
        MEMORY_CLOSEOUT_TOOL_IMPLEMENTATION_VERSION,
    )


def complete_memory_review(ctx: ToolContext) -> dict[str, Any]:
    state = ctx.memory_closeout
    if state is None:
        return {
            "ok": False,
            "error": {
                "code": "memory_closeout_unavailable",
                "message": "Memory closeout is not enabled for this run.",
            },
        }

    result = state.complete(turn=ctx.turn)
    if result.get("ok") is True and result.get("already_completed") is False:
        ctx.log.add_memory_closeout(
            "memory_review_completed",
            turn=ctx.turn,
            outcome=result["outcome"],
            proposal_counts=result["proposal_counts"],
            callback_dispositions=result["callback_dispositions"],
        )
        if result["outcome"] == "no_op":
            ctx.log.add_memory_closeout(
                "memory_review_noop",
                turn=ctx.turn,
                memory_writes_enabled=state.memory_writes_enabled,
            )
    return result


__all__ = [
    "MEMORY_CLOSEOUT_TOOL_IMPLEMENTATION_VERSION",
    "MEMORY_CLOSEOUT_TOOL_SPECS",
    "complete_memory_review",
    "register_memory_closeout_tools",
]
