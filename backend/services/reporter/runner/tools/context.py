"""Context object injected into runner v2 tools."""

from __future__ import annotations

from dataclasses import dataclass

from backend.services.reporter.runner.run_log import RunLog
from backend.services.reporter.runner.state import ArtifactStore, ProcedureState


@dataclass
class ToolContext:
    artifacts: ArtifactStore
    procedures: ProcedureState
    log: RunLog
    turn: int = 0
