"""V2 report brief, article, and supporting schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BriefMeta(BaseModel):
    league_name: str = ""
    league_id: str = ""
    week_start: int = 0
    week_end: int = 0
    article_type: str = "custom"


class Fact(BaseModel):
    id: str
    claim_text: str
    data_refs: list[str] = Field(default_factory=list)
    numbers: dict[str, Any] = Field(default_factory=dict)
    category: str = "general"


class Storyline(BaseModel):
    id: str
    headline: str
    summary: str
    supporting_fact_ids: list[str] = Field(default_factory=list)
    priority: int = Field(default=2, ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    revision_at_set: int = 0


class Section(BaseModel):
    title: str
    bullet_points: list[str] = Field(default_factory=list)
    required_fact_ids: list[str] = Field(default_factory=list)
    storyline_ids: list[str] = Field(default_factory=list)


class Outline(BaseModel):
    sections: list[Section] = Field(default_factory=list)
    revision_at_set: int = 0


class ResolvedStyle(BaseModel):
    voice: str = "sports columnist"
    pacing: str = "moderate"
    humor_level: int = Field(default=1, ge=0, le=3)
    formality: str = "casual"


class ResolvedBias(BaseModel):
    favored_teams: list[str] = Field(default_factory=list)
    disfavored_teams: list[str] = Field(default_factory=list)
    intensity: int = Field(default=0, ge=0, le=3)
    framing_rules: list[str] = Field(default_factory=list)


class MemoryCallback(BaseModel):
    id: str
    callback_type: str
    claim_text: str
    old_event_fact_id: str
    current_event_fact_id: str
    why_now: str
    interestingness_reason: str = ""
    memory_refs: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ReportBrief(BaseModel):
    revision: int = 0
    meta: BriefMeta = Field(default_factory=BriefMeta)
    facts: list[Fact] = Field(default_factory=list)
    memory_callbacks: list[MemoryCallback] = Field(default_factory=list)
    storylines: list[Storyline] = Field(default_factory=list)
    outline: Outline = Field(default_factory=Outline)
    style: ResolvedStyle = Field(default_factory=ResolvedStyle)
    bias: ResolvedBias = Field(default_factory=ResolvedBias)

    def get_fact(self, fact_id: str) -> Fact | None:
        for fact in self.facts:
            if fact.id == fact_id:
                return fact
        return None

    def get_memory_callback(self, callback_id: str) -> MemoryCallback | None:
        for callback in self.memory_callbacks:
            if callback.id == callback_id:
                return callback
        return None

    def bump_revision(self) -> int:
        self.revision += 1
        return self.revision

    def staleness_info(self) -> dict[str, Any]:
        """Return staleness flags for outline and storylines."""
        info: dict[str, Any] = {}
        if self.outline.sections and self.outline.revision_at_set < self.revision:
            gap = self.revision - self.outline.revision_at_set
            info["outline_stale"] = True
            info["outline_gap"] = f"{gap} mutation(s) since outline was set"

        stale_storylines = []
        for storyline in self.storylines:
            if storyline.revision_at_set < self.revision:
                stale_storylines.append(storyline.id)
        if stale_storylines:
            info["stale_storyline_ids"] = stale_storylines
        return info


class ArticleSection(BaseModel):
    name: str
    content: str


class Article(BaseModel):
    sections: list[ArticleSection] = Field(default_factory=list)
    section_order: list[str] = Field(default_factory=list)

    def get_section(self, name: str) -> ArticleSection | None:
        for section in self.sections:
            if section.name == name:
                return section
        return None

    def set_section(self, name: str, content: str) -> None:
        existing = self.get_section(name)
        if existing:
            existing.content = content
        else:
            self.sections.append(ArticleSection(name=name, content=content))
            self.section_order.append(name)

    def to_markdown(self) -> str:
        ordered = self.section_order or [section.name for section in self.sections]
        parts = []
        for name in ordered:
            section = self.get_section(name)
            if section:
                parts.append(section.content)
        return "\n\n".join(parts)


class ArticleOutput(BaseModel):
    article: str
    brief: ReportBrief
    run_log_summary: dict[str, Any] = Field(default_factory=dict)
    run_log_entries: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
