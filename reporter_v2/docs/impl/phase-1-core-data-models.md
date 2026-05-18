# Phase 1: Core Data Models

**Goal:** Define all Pydantic schemas for the brief, article, and runner state.
These are the foundation everything else builds on.

**Files to create:**
- `reporter_v2/__init__.py` (empty)
- `reporter_v2/runner/__init__.py` (empty)
- `reporter_v2/runner/schemas.py`
- `reporter_v2/runner/state.py`
- `reporter_v2/tests/__init__.py` (empty)
- `reporter_v2/tests/conftest.py`
- `reporter_v2/tests/test_schemas.py`

**Dependencies:** None (first phase)

---

## `reporter_v2/runner/schemas.py`

This file defines the v2 `ReportBrief`, `Article`, and supporting types. Key
differences from v1:
- `ReportBrief` has a `revision` counter for staleness tracking
- `Storyline` has `revision_at_set` for staleness tracking
- `Outline` is a wrapper with `revision_at_set`
- `Article` is a new type with ordered named sections

```python
# reporter_v2/runner/schemas.py
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


class ReportBrief(BaseModel):
    revision: int = 0
    meta: BriefMeta = Field(default_factory=BriefMeta)
    facts: list[Fact] = Field(default_factory=list)
    storylines: list[Storyline] = Field(default_factory=list)
    outline: Outline = Field(default_factory=Outline)
    style: ResolvedStyle = Field(default_factory=ResolvedStyle)
    bias: ResolvedBias = Field(default_factory=ResolvedBias)

    def get_fact(self, fact_id: str) -> Fact | None:
        for f in self.facts:
            if f.id == fact_id:
                return f
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
        for s in self.storylines:
            if s.revision_at_set < self.revision:
                stale_storylines.append(s.id)
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
        for s in self.sections:
            if s.name == name:
                return s
        return None

    def set_section(self, name: str, content: str) -> None:
        existing = self.get_section(name)
        if existing:
            existing.content = content
        else:
            self.sections.append(ArticleSection(name=name, content=content))
            self.section_order.append(name)

    def to_markdown(self) -> str:
        ordered = self.section_order or [s.name for s in self.sections]
        parts = []
        for name in ordered:
            sec = self.get_section(name)
            if sec:
                parts.append(sec.content)
        return "\n\n".join(parts)


class ArticleOutput(BaseModel):
    article: str
    brief: ReportBrief
    run_log_summary: dict[str, Any] = Field(default_factory=dict)
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
```

## `reporter_v2/runner/state.py`

```python
# reporter_v2/runner/state.py
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
    model: str | None = None
```

## Tests

`reporter_v2/tests/test_schemas.py`:
- `TestFact`: create fact, verify defaults
- `TestStoryline`: create with `revision_at_set`, verify priority bounds
- `TestReportBrief`: test `bump_revision`, `get_fact`, `staleness_info`
- `TestArticle`: test `set_section`, `get_section`, `to_markdown`, section ordering
- `TestArticleOutput`: roundtrip serialization

All pure unit tests, no mocks needed. Run with `pytest reporter_v2/tests/test_schemas.py`.
