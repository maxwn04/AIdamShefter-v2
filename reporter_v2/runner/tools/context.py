"""Context object injected into runner v2 tools."""

from __future__ import annotations

from dataclasses import dataclass

from reporter_v2.runner.run_log import RunLog
from reporter_v2.runner.state import ArtifactStore, ProcedureState


@dataclass
class ToolContext:
    artifacts: ArtifactStore
    procedures: ProcedureState
    log: RunLog
    turn: int = 0
