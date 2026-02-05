"""Simplified configuration for article generation.

This replaces the preset-heavy ReportSpec with a minimal ReportConfig
that lets the agent drive the research and structure decisions.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TimeRange(BaseModel):
    """Time range for article coverage."""

    week_start: int = Field(description="Starting week (inclusive)")
    week_end: int = Field(description="Ending week (inclusive)")

    @classmethod
    def single_week(cls, week: int) -> TimeRange:
        """Create a range for a single week."""
        return cls(week_start=week, week_end=week)

    @classmethod
    def range(cls, start: int, end: int) -> TimeRange:
        """Create a multi-week range."""
        return cls(week_start=start, week_end=end)


class ToneControls(BaseModel):
    """Tone knobs for article voice."""

    snark_level: int = Field(
        default=1, ge=0, le=3, description="0=none, 1=light, 2=moderate, 3=savage"
    )
    hype_level: int = Field(
        default=1, ge=0, le=3, description="0=reserved, 1=normal, 2=energetic, 3=maximum"
    )
    seriousness: int = Field(
        default=1, ge=0, le=3, description="0=playful, 1=balanced, 2=serious, 3=grave"
    )


class BiasProfile(BaseModel):
    """Bias configuration for article framing.

    Bias affects FRAMING only, never facts. The agent will:
    - Use more positive language for favored teams
    - Use more critical/mocking language for disfavored teams
    - Never change actual scores, records, or statistics
    """

    favored_teams: list[str] = Field(
        default_factory=list, description="Teams to frame positively"
    )
    disfavored_teams: list[str] = Field(
        default_factory=list, description="Teams to frame negatively/mockingly"
    )
    intensity: int = Field(
        default=1,
        ge=0,
        le=3,
        description="0=neutral, 1=subtle, 2=noticeable, 3=heavy",
    )


class ReportConfig(BaseModel):
    """Minimal configuration for article generation.

    This config provides guardrails and preferences but leaves research
    strategy and article structure to the agent.
    """

    # What to cover
    time_range: TimeRange = Field(description="Week or week range to cover")
    focus_hints: list[str] = Field(
        default_factory=list,
        description="Topics to emphasize: 'upsets', 'trades', 'playoff race', etc.",
    )
    avoid_topics: list[str] = Field(
        default_factory=list, description="Topics to skip or minimize"
    )
    focus_teams: list[str] = Field(
        default_factory=list, description="Specific teams to emphasize"
    )

    # Voice & Style
    voice: str = Field(
        default="sports columnist",
        description="Writing persona: 'snarky columnist', 'hype broadcaster', 'noir detective', etc.",
    )
    tone: ToneControls = Field(default_factory=ToneControls)
    profanity_policy: str = Field(
        default="none", description="'none', 'mild', or 'unrestricted'"
    )

    # Bias (framing only, never facts)
    bias_profile: Optional[BiasProfile] = Field(
        default=None, description="Optional bias for team framing"
    )

    # Guardrails
    length_target: int = Field(default=1000, description="Target word count")
    evidence_policy: str = Field(
        default="standard",
        description="'strict' (every number sourced), 'standard', or 'relaxed'",
    )

    # Freeform user guidance
    custom_instructions: str = Field(
        default="",
        description="Raw user instructions to pass to the agent",
    )

    @classmethod
    def for_week(
        cls,
        week: int,
        *,
        voice: str = "sports columnist",
        snark_level: int = 1,
        hype_level: int = 1,
        focus_hints: Optional[list[str]] = None,
        custom_instructions: str = "",
    ) -> ReportConfig:
        """Convenience constructor for a single-week report."""
        return cls(
            time_range=TimeRange.single_week(week),
            voice=voice,
            tone=ToneControls(snark_level=snark_level, hype_level=hype_level),
            focus_hints=focus_hints or [],
            custom_instructions=custom_instructions,
        )

    @classmethod
    def for_week_range(
        cls,
        week_start: int,
        week_end: int,
        *,
        voice: str = "sports columnist",
        focus_hints: Optional[list[str]] = None,
    ) -> ReportConfig:
        """Convenience constructor for a multi-week report."""
        return cls(
            time_range=TimeRange.range(week_start, week_end),
            voice=voice,
            focus_hints=focus_hints or [],
        )

    def with_bias(
        self,
        favored: Optional[list[str]] = None,
        disfavored: Optional[list[str]] = None,
        intensity: int = 2,
    ) -> ReportConfig:
        """Return a copy with bias configuration added."""
        data = self.model_dump()
        data["bias_profile"] = BiasProfile(
            favored_teams=favored or [],
            disfavored_teams=disfavored or [],
            intensity=intensity,
        )
        return ReportConfig.model_validate(data)

    def get_bias_instructions(self) -> str:
        """Generate bias instructions for the writing prompt."""
        if not self.bias_profile:
            return ""

        bp = self.bias_profile
        if not bp.favored_teams and not bp.disfavored_teams:
            return ""

        lines = ["## Bias Instructions (framing only, never change facts)"]

        if bp.favored_teams:
            teams = ", ".join(bp.favored_teams)
            if bp.intensity == 1:
                lines.append(f"- Use positive language when describing {teams}")
            elif bp.intensity == 2:
                lines.append(f"- Frame {teams} enthusiastically; lead with their positives")
            else:  # 3
                lines.append(f"- Celebrate {teams} with high energy; position as contenders")

        if bp.disfavored_teams:
            teams = ", ".join(bp.disfavored_teams)
            if bp.intensity == 1:
                lines.append(f"- Use neutral/brief language for {teams}")
            elif bp.intensity == 2:
                lines.append(f"- Frame {teams}'s struggles as expected; light teasing allowed")
            else:  # 3
                lines.append(f"- Roast {teams} playfully; emphasize their failures")

        lines.append("- NEVER change actual scores, records, or statistics")
        return "\n".join(lines)
