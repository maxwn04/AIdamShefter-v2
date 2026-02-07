"""Legacy specs module - kept for backwards compatibility.

DEPRECATED: This module is deprecated. Use agent.config.ReportConfig instead.

The preset-based system has been replaced with an iterative research approach
where the agent decides what to research and how to structure the article.
"""

from __future__ import annotations

import warnings
from typing import Optional
from pydantic import BaseModel, Field

# Re-export from config for backwards compatibility
from reporter.agent.config import (
    TimeRange,
    ToneControls,
    BiasProfile,
    ReportConfig,
)


def _deprecation_warning(name: str):
    warnings.warn(
        f"{name} is deprecated. Use agent.config.ReportConfig instead. "
        "The preset system has been replaced with iterative research.",
        DeprecationWarning,
        stacklevel=3,
    )


# Legacy ArticleRequest - still used for parsing user input
class ArticleRequest(BaseModel):
    """User's raw request before processing.

    DEPRECATED: This is kept for backwards compatibility.
    Use ReporterAgent.run(request, week=N, ...) directly instead.
    """

    raw_request: str = Field(description="The user's natural language request")
    preset: Optional[str] = Field(
        default=None, description="DEPRECATED: Presets are no longer used"
    )
    week: Optional[int] = Field(default=None, description="Target week if specified")
    overrides: dict = Field(
        default_factory=dict, description="DEPRECATED: Use kwargs instead"
    )


# Legacy ReportSpec - aliased to ReportConfig
ReportSpec = ReportConfig


# Legacy preset constants - these now just return default configs
def get_preset(name: str) -> Optional[ReportConfig]:
    """Get a preset ReportConfig by name.

    DEPRECATED: Presets are deprecated. The agent now decides structure dynamically.
    This function returns a basic ReportConfig for backwards compatibility.
    """
    _deprecation_warning("get_preset")

    # Return a basic config - the agent will handle the rest
    return ReportConfig(
        time_range=TimeRange(week_start=1, week_end=1),
    )


# Legacy preset templates - deprecated
WEEKLY_RECAP_PRESET = ReportConfig(
    time_range=TimeRange(week_start=1, week_end=1),
    voice="sports columnist",
    tone=ToneControls(snark_level=1, hype_level=2),
)

POWER_RANKINGS_PRESET = ReportConfig(
    time_range=TimeRange(week_start=1, week_end=1),
    voice="analytical sports writer",
    tone=ToneControls(snark_level=1, hype_level=1, seriousness=2),
)

TEAM_DEEP_DIVE_PRESET = ReportConfig(
    time_range=TimeRange(week_start=1, week_end=1),
    voice="beat reporter",
    tone=ToneControls(snark_level=0, hype_level=1, seriousness=2),
)

PLAYOFF_REACTION_PRESET = ReportConfig(
    time_range=TimeRange(week_start=1, week_end=1),
    voice="hype broadcaster",
    tone=ToneControls(snark_level=1, hype_level=3),
)

PRESETS = {
    "weekly_recap": WEEKLY_RECAP_PRESET,
    "power_rankings": POWER_RANKINGS_PRESET,
    "team_deep_dive": TEAM_DEEP_DIVE_PRESET,
    "playoff_reaction": PLAYOFF_REACTION_PRESET,
}
