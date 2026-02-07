"""ReportBrief and output schemas for the reporter agent."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Union, TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from reporter.agent.config import ReportConfig
    from reporter.agent.research_log import ResearchLog


class BriefMeta(BaseModel):
    """Metadata for a report brief."""

    league_name: str = Field(default="", description="Name of the fantasy league")
    league_id: str = Field(default="", description="League identifier")
    week_start: int = Field(description="Starting week covered")
    week_end: int = Field(description="Ending week covered")
    article_type: str = Field(
        default="custom", description="Type of article (always 'custom' in new system)"
    )
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class Fact(BaseModel):
    """A single verified fact from the datalayer.

    Facts are the atomic units of truth. Every claim in the article
    should trace back to one or more facts.
    """

    id: str = Field(description="Unique identifier for this fact")
    claim_text: str = Field(description="Human-readable statement of the fact")
    data_refs: list[str] = Field(
        default_factory=list,
        description="Tool calls that sourced this fact, e.g. 'get_week_games:week=5'",
    )
    numbers: dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted numeric values, e.g. {'points': 142.3, 'week': 5}",
    )
    category: str = Field(
        default="general",
        description="Fact category: score, standing, transaction, player, etc.",
    )


class Storyline(BaseModel):
    """A narrative thread identified from facts.

    Storylines are the building blocks of the article's narrative.
    Each storyline weaves together related facts into a coherent mini-narrative.
    """

    id: str = Field(description="Unique identifier for this storyline")
    headline: str = Field(description="Catchy headline, e.g. 'Cinderella Run Ends'")
    summary: str = Field(description="2-3 sentence narrative summary")
    supporting_fact_ids: list[str] = Field(
        default_factory=list,
        description="References to Fact.id that support this storyline",
    )
    priority: int = Field(
        default=2, ge=1, le=5, description="1=lead story, 5=minor mention"
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Tags like 'upset', 'rivalry', 'streak', 'trade'",
    )


class Section(BaseModel):
    """A planned section of the article."""

    title: str = Field(description="Section heading")
    bullet_points: list[str] = Field(
        default_factory=list, description="Key points to cover"
    )
    required_fact_ids: list[str] = Field(
        default_factory=list, description="Facts that must be mentioned"
    )
    storyline_ids: list[str] = Field(
        default_factory=list, description="Storylines to weave in"
    )


class ResolvedStyle(BaseModel):
    """Resolved style configuration for writing."""

    voice: str = Field(default="sports columnist", description="Writing voice/persona")
    pacing: str = Field(
        default="moderate", description="fast, moderate, deliberate"
    )
    humor_level: int = Field(default=1, ge=0, le=3)
    formality: str = Field(default="casual", description="formal, casual, irreverent")


class ResolvedBias(BaseModel):
    """Resolved bias rules for writing."""

    favored_teams: list[str] = Field(default_factory=list)
    disfavored_teams: list[str] = Field(default_factory=list)
    intensity: int = Field(default=0, ge=0, le=3)
    framing_rules: list[str] = Field(
        default_factory=list,
        description="Specific framing instructions, e.g. 'emphasize wins, downplay losses'",
    )


class ReportBrief(BaseModel):
    """The backbone of reliability - captures what the agent believes after research.

    The brief is built during the research phase and consumed during drafting.
    It serves as the contract between research and writing, ensuring all claims
    in the article are grounded in verified facts.
    """

    # Meta
    meta: BriefMeta = Field(
        default_factory=BriefMeta, description="Article and league metadata"
    )

    # Facts (the evidence base)
    facts: list[Fact] = Field(
        default_factory=list, description="All verified facts from research"
    )

    # Storylines (narrative structure)
    storylines: list[Storyline] = Field(
        default_factory=list, description="Identified narrative threads"
    )

    # Outline (writing plan)
    outline: list[Section] = Field(
        default_factory=list, description="Planned article sections"
    )

    # Resolved style/bias
    style: ResolvedStyle = Field(default_factory=ResolvedStyle)
    bias: ResolvedBias = Field(default_factory=ResolvedBias)

    def get_fact(self, fact_id: str) -> Optional[Fact]:
        """Look up a fact by ID."""
        for fact in self.facts:
            if fact.id == fact_id:
                return fact
        return None

    def get_facts_by_category(self, category: str) -> list[Fact]:
        """Get all facts in a category."""
        return [f for f in self.facts if f.category == category]

    def get_lead_storylines(self, max_priority: int = 2) -> list[Storyline]:
        """Get the top-priority storylines."""
        return [s for s in self.storylines if s.priority <= max_priority]


class ClaimMismatch(BaseModel):
    """A discrepancy between article and brief."""

    claim_text: str = Field(description="The claim from the article")
    expected_value: Optional[str] = Field(
        default=None, description="What the brief says"
    )
    actual_value: Optional[str] = Field(
        default=None, description="What the article says"
    )
    fact_id: Optional[str] = Field(default=None, description="Related fact ID if found")
    severity: str = Field(default="error", description="error, warning, info")


class VerificationResult(BaseModel):
    """Result of verifying article against brief."""

    passed: bool = Field(description="Whether verification passed")
    claims_checked: int = Field(description="Number of claims verified")
    claims_matched: int = Field(description="Number of claims that matched")
    mismatches: list[ClaimMismatch] = Field(default_factory=list)
    corrections_made: list[str] = Field(default_factory=list)


class ArticleOutput(BaseModel):
    """Complete output from an article generation run."""

    article: str = Field(description="The final article in Markdown")
    config: "ReportConfig" = Field(description="The ReportConfig used")
    brief: ReportBrief = Field(description="The research brief")
    research_log: Optional["ResearchLog"] = Field(
        default=None, description="Full research log with reasoning"
    )
    verification: Optional[VerificationResult] = Field(
        default=None, description="Verification results if run"
    )
    trace_id: Optional[str] = Field(
        default=None, description="Trace ID for debugging"
    )
    generated_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )

    def get_research_log_markdown(self) -> str:
        """Export the research log as readable markdown."""
        if self.research_log is None:
            return "No research log available."
        return self.research_log.to_markdown()

    class Config:
        arbitrary_types_allowed = True


# Rebuild models to resolve forward references after all classes are defined
def _rebuild_models():
    from reporter.agent.config import ReportConfig
    from reporter.agent.research_log import ResearchLog

    ArticleOutput.model_rebuild()


_rebuild_models()
