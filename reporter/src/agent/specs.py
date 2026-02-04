"""ReportSpec and related models for article configuration."""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ArticleType(str, Enum):
    """Supported article types."""

    WEEKLY_RECAP = "weekly_recap"
    POWER_RANKINGS = "power_rankings"
    TEAM_DEEP_DIVE = "team_deep_dive"
    PLAYOFF_REACTION = "playoff_reaction"
    CUSTOM = "custom"


class ProfanityPolicy(str, Enum):
    """Profanity level in articles."""

    NONE = "none"
    MILD = "mild"
    UNRESTRICTED = "unrestricted"


class EvidencePolicy(str, Enum):
    """How strictly facts must be grounded."""

    STRICT = "strict"  # Every number needs a data_ref
    STANDARD = "standard"  # Key claims grounded, flavor allowed
    RELAXED = "relaxed"  # Major facts grounded, stylistic liberties ok


class POV(str, Enum):
    """Point of view for writing."""

    FIRST_PERSON = "first_person"
    THIRD_PERSON = "third_person"
    SECOND_PERSON = "second_person"


class TimeRange(BaseModel):
    """Time range for article coverage."""

    week_start: int = Field(description="Starting week (inclusive)")
    week_end: int = Field(description="Ending week (inclusive)")

    @classmethod
    def single_week(cls, week: int) -> TimeRange:
        return cls(week_start=week, week_end=week)

    @classmethod
    def range(cls, start: int, end: int) -> TimeRange:
        return cls(week_start=start, week_end=end)


class ToneControls(BaseModel):
    """Tone knobs for article voice."""

    snark_level: int = Field(default=1, ge=0, le=3, description="0=none, 3=savage")
    hype_level: int = Field(default=1, ge=0, le=3, description="0=reserved, 3=maximum")
    seriousness: int = Field(default=1, ge=0, le=3, description="0=playful, 3=grave")


class BiasProfile(BaseModel):
    """Bias configuration for article framing."""

    favored_teams: list[str] = Field(
        default_factory=list, description="Teams to frame positively"
    )
    disfavored_teams: list[str] = Field(
        default_factory=list, description="Teams to frame negatively"
    )
    intensity: int = Field(
        default=1, ge=0, le=3, description="0=neutral, 1=subtle, 2=noticeable, 3=heavy"
    )


class SectionSpec(BaseModel):
    """Specification for a single article section."""

    title: str
    description: str = ""
    required: bool = True


class StructureSpec(BaseModel):
    """Article structure specification."""

    sections: list[SectionSpec] = Field(default_factory=list)
    freeform: bool = Field(
        default=False, description="If true, agent chooses structure"
    )


class ReportSpec(BaseModel):
    """The contract defining what gets researched and how it's presented.

    This is the central configuration that drives research, writing, and verification.
    """

    # Identity
    article_type: ArticleType = Field(description="Type of article to generate")
    time_range: TimeRange = Field(description="Week range to cover")

    # Voice & Style
    genre_voice: str = Field(
        default="sports columnist",
        description="Voice persona: 'sports radio', 'noir detective', etc.",
    )
    tone_controls: ToneControls = Field(default_factory=ToneControls)
    profanity_policy: ProfanityPolicy = Field(default=ProfanityPolicy.NONE)

    # Structure
    structure: StructureSpec = Field(default_factory=StructureSpec)
    length_target: int = Field(default=1000, description="Target word count")
    pov: POV = Field(default=POV.THIRD_PERSON)

    # Content
    content_requirements: list[str] = Field(
        default_factory=list, description="Must-cover topics"
    )
    focus_teams: list[str] = Field(
        default_factory=list, description="Teams to emphasize"
    )

    # Bias
    bias_profile: Optional[BiasProfile] = None

    # Guardrails
    evidence_policy: EvidencePolicy = Field(default=EvidencePolicy.STANDARD)
    audience: str = Field(default="league members")

    def is_complete(self) -> bool:
        """Check if spec has all required fields for processing."""
        return self.article_type is not None and self.time_range is not None


class ArticleRequest(BaseModel):
    """User's raw request before spec synthesis."""

    raw_request: str = Field(description="The user's natural language request")
    preset: Optional[str] = Field(
        default=None, description="Optional preset name to use as base"
    )
    week: Optional[int] = Field(default=None, description="Target week if specified")
    overrides: dict = Field(
        default_factory=dict, description="Explicit field overrides"
    )


# Preset templates
WEEKLY_RECAP_PRESET = ReportSpec(
    article_type=ArticleType.WEEKLY_RECAP,
    time_range=TimeRange(week_start=1, week_end=1),  # Will be overridden
    genre_voice="sports columnist",
    tone_controls=ToneControls(snark_level=1, hype_level=2, seriousness=1),
    structure=StructureSpec(
        sections=[
            SectionSpec(title="Introduction", description="Week summary hook"),
            SectionSpec(title="Matchup Highlights", description="Key games"),
            SectionSpec(title="Standings Check", description="Current standings"),
            SectionSpec(title="Transaction Report", description="Trades and pickups"),
            SectionSpec(title="Looking Ahead", description="Next week preview"),
        ]
    ),
    length_target=1000,
    content_requirements=["matchup results", "standings", "top performers"],
)

POWER_RANKINGS_PRESET = ReportSpec(
    article_type=ArticleType.POWER_RANKINGS,
    time_range=TimeRange(week_start=1, week_end=1),
    genre_voice="analytical sports writer",
    tone_controls=ToneControls(snark_level=1, hype_level=1, seriousness=2),
    structure=StructureSpec(
        sections=[
            SectionSpec(title="Introduction", description="Power rankings preamble"),
            SectionSpec(title="Rankings", description="Ordered team rankings with blurbs"),
            SectionSpec(title="Movers", description="Biggest risers and fallers"),
        ]
    ),
    length_target=1200,
    content_requirements=["all teams ranked", "record and points context"],
)

TEAM_DEEP_DIVE_PRESET = ReportSpec(
    article_type=ArticleType.TEAM_DEEP_DIVE,
    time_range=TimeRange(week_start=1, week_end=1),
    genre_voice="beat reporter",
    tone_controls=ToneControls(snark_level=0, hype_level=1, seriousness=2),
    structure=StructureSpec(
        sections=[
            SectionSpec(title="Team Profile", description="Manager and team identity"),
            SectionSpec(title="Season Arc", description="Performance trajectory"),
            SectionSpec(title="Roster Breakdown", description="Key players"),
            SectionSpec(title="Transaction Activity", description="Roster moves"),
            SectionSpec(title="Outlook", description="Projections and concerns"),
        ]
    ),
    length_target=1500,
    content_requirements=["team record", "roster composition", "key players"],
)

PLAYOFF_REACTION_PRESET = ReportSpec(
    article_type=ArticleType.PLAYOFF_REACTION,
    time_range=TimeRange(week_start=1, week_end=1),
    genre_voice="hype sports broadcaster",
    tone_controls=ToneControls(snark_level=1, hype_level=3, seriousness=1),
    structure=StructureSpec(
        sections=[
            SectionSpec(title="The Stage", description="Playoff stakes"),
            SectionSpec(title="The Games", description="Playoff matchup results"),
            SectionSpec(title="Heroes and Goats", description="Standout players"),
            SectionSpec(title="Championship Preview", description="What's next"),
        ]
    ),
    length_target=1000,
    content_requirements=["playoff matchups", "winners and losers", "key performers"],
)

PRESETS = {
    "weekly_recap": WEEKLY_RECAP_PRESET,
    "power_rankings": POWER_RANKINGS_PRESET,
    "team_deep_dive": TEAM_DEEP_DIVE_PRESET,
    "playoff_reaction": PLAYOFF_REACTION_PRESET,
}


def get_preset(name: str) -> Optional[ReportSpec]:
    """Get a preset ReportSpec by name."""
    return PRESETS.get(name.lower())
