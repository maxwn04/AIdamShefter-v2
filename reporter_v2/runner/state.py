"""Runner state containers."""

from __future__ import annotations

from pydantic import BaseModel, Field

from reporter_v2.runner.schemas import Article, ReportBrief


class ArtifactStore(BaseModel):
    brief: ReportBrief = Field(default_factory=ReportBrief)
    article: Article = Field(default_factory=Article)


class ProcedureState(BaseModel):
    active: str | None = None


class RunnerConfig(BaseModel):
    soft_tool_limit: int = 40
    hard_tool_limit: int = 50
    max_turns: int = 60
    model: str = "gpt-5-mini"
