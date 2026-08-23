"""Procedure-loading tools for the reporter v2 runner."""

from __future__ import annotations

import json
from pathlib import Path

from backend.services.reporter.runner.models import ToolDef
from backend.services.reporter.runner.tools.context import ToolContext
from backend.services.reporter.runner.tools.registry import ToolRegistry


PROCEDURE_DIR = Path(__file__).parent.parent.parent / "procedures"
VALID_PROCEDURES = {"research", "storyline", "drafting", "verification"}
PROCEDURE_TOOL_IMPLEMENTATION_VERSION = "1"

PROCEDURE_TOOL_SPECS: list[ToolDef] = [
    {
        "type": "function",
        "function": {
            "name": "load_procedure",
            "description": (
                "Load the current operating procedure. Use this before research, "
                "storyline synthesis, drafting, and verification work."
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


def register_procedure_tools(registry: ToolRegistry) -> None:
    """Register procedure-loading tools against a ToolRegistry."""
    registry.register_context_tool(
        "load_procedure",
        load_procedure,
        PROCEDURE_TOOL_SPECS[0],
        PROCEDURE_TOOL_IMPLEMENTATION_VERSION,
    )


def load_procedure(ctx: ToolContext, *, name: str) -> str:
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

    path = PROCEDURE_DIR / f"{name}.md"
    if not path.exists():
        return json.dumps({"error": f"Procedure file not found: {path}"})

    previous = ctx.procedures.active
    ctx.procedures.active = name
    ctx.log.add_procedure_switch(previous, name, turn=ctx.turn)

    return path.read_text(encoding="utf-8")
