"""Runner state containers."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from reporter_v2.runner.schemas import Article, ReportBrief


class ProcedureHistoryMode(str, Enum):
    REPLACE = "replace"
    APPEND = "append"


class ArtifactStore(BaseModel):
    brief: ReportBrief = Field(default_factory=ReportBrief)
    article: Article = Field(default_factory=Article)


class ProcedureState(BaseModel):
    active: str | None = None


class RunnerConfig(BaseModel):
    max_turns: int = 60
    procedure_history_mode: ProcedureHistoryMode = ProcedureHistoryMode.REPLACE
