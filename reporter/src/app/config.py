"""Configuration for the reporter application."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from dotenv import load_dotenv


class ReporterConfig(BaseModel):
    """Configuration for the reporter agent."""

    # Sleeper configuration
    sleeper_league_id: str = Field(description="Sleeper league ID")
    sleeper_week_override: Optional[int] = Field(
        default=None, description="Override the current week"
    )

    # Model configuration
    model: str = Field(default="gpt-4o", description="LLM model to use")
    openai_api_key: Optional[str] = Field(
        default=None, description="OpenAI API key (can also use OPENAI_API_KEY env)"
    )

    # Output configuration
    output_dir: Path = Field(
        default=Path(".output"), description="Directory for generated articles"
    )

    # Tracing
    tracing_enabled: bool = Field(default=True, description="Enable tracing")


def load_config() -> ReporterConfig:
    """Load configuration from environment variables."""
    load_dotenv()

    league_id = os.getenv("SLEEPER_LEAGUE_ID")
    if not league_id:
        raise ValueError("SLEEPER_LEAGUE_ID environment variable is required")

    week_override_str = os.getenv("SLEEPER_WEEK_OVERRIDE")
    week_override = int(week_override_str) if week_override_str else None

    output_dir_str = os.getenv("REPORTER_OUTPUT_DIR", ".output")
    output_dir = Path(output_dir_str)

    return ReporterConfig(
        sleeper_league_id=league_id,
        sleeper_week_override=week_override,
        model=os.getenv("REPORTER_MODEL", "gpt-4o"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        output_dir=output_dir,
        tracing_enabled=os.getenv("REPORTER_TRACING", "true").lower() == "true",
    )


# Default style presets for CLI
STYLE_PRESETS = {
    "straight": {"snark_level": 0, "hype_level": 1, "seriousness": 2},
    "hype": {"snark_level": 0, "hype_level": 3, "seriousness": 0},
    "snarky": {"snark_level": 2, "hype_level": 1, "seriousness": 1},
    "savage": {"snark_level": 3, "hype_level": 1, "seriousness": 0},
}
