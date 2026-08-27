"""Procedure-loading tools for the reporter v2 runner."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from backend.services.reporter.runner.models import ToolDef
from backend.services.reporter.runner.tools.context import ToolContext
from backend.services.reporter.runner.tools.registry import ToolRegistry


PROCEDURE_DIR = Path(__file__).parent.parent.parent / "procedures"
VALID_PROCEDURES = {"research", "storyline", "drafting", "verification"}
PROCEDURE_TOOL_IMPLEMENTATION_VERSION = "4"

PROCEDURE_TOOL_SPECS: list[ToolDef] = [
    {
        "type": "function",
        "function": {
            "name": "load_procedure",
            "description": (
                "Load goal-oriented editorial guidance when an unmet reporter goal "
                "would benefit from it. Guides do not gate tools or define workflow "
                "stages, and they need not be loaded in sequence."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "enum": sorted(VALID_PROCEDURES),
                    },
                },
                "required": ["name"],
            },
        },
    },
]


def register_procedure_tools(
    registry: ToolRegistry,
    procedures: Mapping[str, str] | None = None,
) -> None:
    """Register procedure-loading tools against a ToolRegistry."""
    frozen_procedures = dict(procedures) if procedures is not None else None

    def handler(ctx: ToolContext, *, name: str) -> str:
        return load_procedure(ctx, name=name, procedures=frozen_procedures)

    registry.register_context_tool(
        "load_procedure",
        handler,
        PROCEDURE_TOOL_SPECS[0],
        PROCEDURE_TOOL_IMPLEMENTATION_VERSION,
    )


def load_procedure(
    ctx: ToolContext,
    *,
    name: str,
    procedures: Mapping[str, str] | None = None,
) -> str:
    """Load a procedure by name and return its markdown text."""
    if name not in VALID_PROCEDURES:
        return json.dumps(
            {
                "error": (
                    f"Unknown procedure: {name}. "
                    f"Valid: {sorted(VALID_PROCEDURES)}"
                )
            }
        )

    if procedures is None:
        path = PROCEDURE_DIR / f"{name}.md"
        if not path.exists():
            return json.dumps({"error": f"Procedure file not found: {path}"})
        content = path.read_text(encoding="utf-8")
    else:
        content = procedures.get(name)
        if content is None:
            return json.dumps({"error": f"Procedure content not prepared: {name}"})

    previous = ctx.procedures.active
    ctx.procedures.active = name
    ctx.log.add_procedure_switch(previous, name, turn=ctx.turn)

    return content
