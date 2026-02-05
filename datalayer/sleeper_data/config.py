"""Configuration helpers for Sleeper data layer."""

from __future__ import annotations

from dataclasses import dataclass
import os
from dotenv import load_dotenv


@dataclass(frozen=True)
class SleeperConfig:
    league_id: str
    week_override: int | None = None


def load_config() -> SleeperConfig:
    load_dotenv()
    league_id = os.getenv("SLEEPER_LEAGUE_ID")
    if not league_id:
        raise ValueError("SLEEPER_LEAGUE_ID must be set.")

    override_raw = os.getenv("SLEEPER_WEEK_OVERRIDE")
    if override_raw is None or override_raw == "":
        week_override = None
    else:
        try:
            week_override = int(override_raw)
        except ValueError as exc:
            raise ValueError("SLEEPER_WEEK_OVERRIDE must be an integer.") from exc

    return SleeperConfig(league_id=str(league_id), week_override=week_override)
