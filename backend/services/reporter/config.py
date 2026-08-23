"""Configuration models for reporter v2 article generation."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TimeRange(BaseModel):
    """Time range for article coverage."""

    week_start: int = Field(description="Starting week, inclusive")
    week_end: int = Field(description="Ending week, inclusive")

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

    snark_level: int = Field(default=1, ge=0, le=3)
    hype_level: int = Field(default=1, ge=0, le=3)
    seriousness: int = Field(default=1, ge=0, le=3)


class BiasProfile(BaseModel):
    """Bias configuration for framing only, never facts."""

    favored_teams: list[str] = Field(default_factory=list)
    disfavored_teams: list[str] = Field(default_factory=list)
    intensity: int = Field(default=1, ge=0, le=3)


class ReportConfig(BaseModel):
    """User-facing article generation configuration."""

    time_range: TimeRange
    focus_hints: list[str] = Field(default_factory=list)
    avoid_topics: list[str] = Field(default_factory=list)
    focus_teams: list[str] = Field(default_factory=list)

    voice: str = "sports columnist"
    tone: ToneControls = Field(default_factory=ToneControls)
    profanity_policy: str = "none"

    bias_profile: BiasProfile | None = None

    length_target: int = 1000
    evidence_policy: str = "standard"

    custom_instructions: str = ""

    @classmethod
    def for_week(
        cls,
        week: int,
        *,
        voice: str = "sports columnist",
        snark_level: int = 1,
        hype_level: int = 1,
        focus_hints: list[str] | None = None,
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
        focus_hints: list[str] | None = None,
    ) -> ReportConfig:
        """Convenience constructor for a multi-week report."""
        return cls(
            time_range=TimeRange.range(week_start, week_end),
            voice=voice,
            focus_hints=focus_hints or [],
        )

    def with_bias(
        self,
        favored: list[str] | None = None,
        disfavored: list[str] | None = None,
        intensity: int = 2,
    ) -> ReportConfig:
        """Return a copy with bias configuration added."""
        return self.model_copy(
            update={
                "bias_profile": BiasProfile(
                    favored_teams=favored or [],
                    disfavored_teams=disfavored or [],
                    intensity=intensity,
                )
            }
        )

    def get_bias_instructions(self) -> str:
        """Generate bias instructions for the model prompt."""
        if not self.bias_profile:
            return ""

        bias = self.bias_profile
        if not bias.favored_teams and not bias.disfavored_teams:
            return ""

        lines = ["## Bias Instructions (framing only, never change facts)"]
        if bias.favored_teams:
            teams = ", ".join(bias.favored_teams)
            if bias.intensity == 1:
                lines.append(f"- Use positive language when describing {teams}")
            elif bias.intensity == 2:
                lines.append(f"- Frame {teams} enthusiastically; lead with positives")
            else:
                lines.append(f"- Celebrate {teams} with high energy")

        if bias.disfavored_teams:
            teams = ", ".join(bias.disfavored_teams)
            if bias.intensity == 1:
                lines.append(f"- Use neutral or brief language for {teams}")
            elif bias.intensity == 2:
                lines.append(f"- Light teasing is allowed when describing {teams}")
            else:
                lines.append(f"- Roast {teams} playfully; emphasize failures")

        lines.append("- NEVER change actual scores, records, or statistics")
        return "\n".join(lines)
