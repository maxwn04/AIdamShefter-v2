"""Immutable reporter inputs prepared before a generation starts."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from backend.services.reporter.runner.models import ToolDef
from backend.services.reporter.runner.tools.artifact_tools import (
    ARTIFACT_TOOL_IMPLEMENTATION_VERSION,
    ARTIFACT_TOOL_SPECS,
)
from backend.services.reporter.runner.tools.brief_tools import (
    BRIEF_TOOL_IMPLEMENTATION_VERSION,
    BRIEF_TOOL_SPECS,
)
from backend.services.reporter.runner.tools.datalayer_tools import (
    DATALAYER_TOOL_IMPLEMENTATION_VERSION,
    DATALAYER_TOOL_SPECS,
)
from backend.services.reporter.runner.tools.memory_closeout_tools import (
    MEMORY_CLOSEOUT_TOOL_IMPLEMENTATION_VERSION,
    MEMORY_CLOSEOUT_TOOL_SPECS,
)
from backend.services.reporter.runner.tools.memory_tools import (
    MEMORY_TOOL_IMPLEMENTATION_VERSION,
    MEMORY_TOOL_SPECS,
)
from backend.services.reporter.runner.tools.procedure_tools import (
    PROCEDURE_DIR,
    PROCEDURE_TOOL_IMPLEMENTATION_VERSION,
    PROCEDURE_TOOL_SPECS,
    VALID_PROCEDURES,
)


class PreparedProcedure(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    content: str


class PreparedTool(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    definition: ToolDef
    implementation_version: str


class PreparedReporterDefinition(BaseModel):
    """The exact prompt, procedures, and tools sealed for one run."""

    model_config = ConfigDict(frozen=True)

    system_prompt: str
    procedures: tuple[PreparedProcedure, ...]
    tools: tuple[PreparedTool, ...]

    @property
    def procedure_contents(self) -> dict[str, str]:
        return {procedure.name: procedure.content for procedure in self.procedures}


def prepare_reporter_definition(
    *,
    memory_enabled: bool,
) -> PreparedReporterDefinition:
    """Read reporter assets once and snapshot its model-facing tool bundle."""

    reporter_dir = Path(__file__).resolve().parent
    system_prompt = (reporter_dir / "prompts" / "system.md").read_text(
        encoding="utf-8"
    ).strip()
    procedure_names = set(VALID_PROCEDURES)
    if memory_enabled:
        procedure_names.add("memory_closeout")
    procedures = tuple(
        PreparedProcedure(
            name=name,
            content=(PROCEDURE_DIR / f"{name}.md").read_text(encoding="utf-8"),
        )
        for name in sorted(procedure_names)
    )
    groups = [
        (ARTIFACT_TOOL_SPECS, ARTIFACT_TOOL_IMPLEMENTATION_VERSION),
        (BRIEF_TOOL_SPECS, BRIEF_TOOL_IMPLEMENTATION_VERSION),
        (PROCEDURE_TOOL_SPECS, PROCEDURE_TOOL_IMPLEMENTATION_VERSION),
        (DATALAYER_TOOL_SPECS, DATALAYER_TOOL_IMPLEMENTATION_VERSION),
    ]
    if memory_enabled:
        groups.append((MEMORY_TOOL_SPECS, MEMORY_TOOL_IMPLEMENTATION_VERSION))
        groups.append(
            (
                MEMORY_CLOSEOUT_TOOL_SPECS,
                MEMORY_CLOSEOUT_TOOL_IMPLEMENTATION_VERSION,
            )
        )

    tools = tuple(
        PreparedTool(
            name=spec["function"]["name"],
            definition=deepcopy(spec),
            implementation_version=version,
        )
        for specs, version in groups
        for spec in specs
    )
    return PreparedReporterDefinition(
        system_prompt=system_prompt,
        procedures=procedures,
        tools=tools,
    )


__all__ = [
    "PreparedProcedure",
    "PreparedReporterDefinition",
    "PreparedTool",
    "prepare_reporter_definition",
]
