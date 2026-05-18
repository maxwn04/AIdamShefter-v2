"""Procedure-loading tools for the reporter v2 runner."""

from __future__ import annotations

import json
from pathlib import Path

from reporter_v2.runner.tools.context import ToolContext


PROCEDURE_DIR = Path(__file__).parent.parent.parent / "procedures"
VALID_PROCEDURES = {"research", "storyline", "drafting", "verification"}


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

