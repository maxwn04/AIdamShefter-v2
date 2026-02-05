"""High-level workflow functions for article generation."""

from __future__ import annotations

import asyncio
from typing import Optional

from datalayer.sleeper_data import SleeperLeagueData

from agent.config import ReportConfig, TimeRange, ToneControls, BiasProfile
from agent.schemas import ArticleOutput
from agent.reporter_agent import ReporterAgent


async def generate_report_async(
    request: str,
    *,
    week: Optional[int] = None,
    data: Optional[SleeperLeagueData] = None,
    model: str = "gpt-4o",
    voice: str = "sports columnist",
    snark_level: int = 1,
    hype_level: int = 1,
    focus_hints: Optional[list[str]] = None,
    focus_teams: Optional[list[str]] = None,
    favored_teams: Optional[list[str]] = None,
    disfavored_teams: Optional[list[str]] = None,
    bias_intensity: int = 2,
    length_target: int = 1000,
) -> ArticleOutput:
    """Generate a fantasy football report asynchronously.

    This is the main entry point for generating articles. The agent will
    research the specified week(s) and write an article based on what it finds.

    Args:
        request: Natural language description of what you want.
            Examples:
            - "Write a weekly recap focusing on upsets"
            - "Snarky recap of this week, roast Team Taco"
            - "Power rankings with analysis"
        week: Week number to cover (defaults to current week).
        data: Optional pre-loaded SleeperLeagueData. If not provided,
              a new instance will be created and loaded.
        model: The model to use for generation.
        voice: Writing voice/persona.
        snark_level: 0-3, how snarky the article should be.
        hype_level: 0-3, how hyped/energetic.
        focus_hints: Topics to emphasize (e.g., ["upsets", "trades"]).
        focus_teams: Teams to give extra attention.
        favored_teams: Teams to frame positively.
        disfavored_teams: Teams to frame negatively/mockingly.
        bias_intensity: 0-3, how strong the bias.
        length_target: Target word count.

    Returns:
        ArticleOutput containing the article, config, brief, and research log.
    """
    # Load data if not provided
    if data is None:
        data = SleeperLeagueData()
        data.load()

    # Use current week if not specified
    if week is None:
        week = data.effective_week

    # Create and run the agent
    agent = ReporterAgent(data, model=model)
    return await agent.run(
        request,
        week=week,
        voice=voice,
        snark_level=snark_level,
        hype_level=hype_level,
        focus_hints=focus_hints,
        focus_teams=focus_teams,
        favored_teams=favored_teams,
        disfavored_teams=disfavored_teams,
        bias_intensity=bias_intensity,
        length_target=length_target,
    )


def generate_report(
    request: str,
    *,
    week: Optional[int] = None,
    data: Optional[SleeperLeagueData] = None,
    model: str = "gpt-4o",
    voice: str = "sports columnist",
    snark_level: int = 1,
    hype_level: int = 1,
    focus_hints: Optional[list[str]] = None,
    focus_teams: Optional[list[str]] = None,
    favored_teams: Optional[list[str]] = None,
    disfavored_teams: Optional[list[str]] = None,
    bias_intensity: int = 2,
    length_target: int = 1000,
) -> ArticleOutput:
    """Generate a fantasy football report synchronously.

    This is a convenience wrapper around generate_report_async.
    See generate_report_async for full documentation.
    """
    return asyncio.run(
        generate_report_async(
            request,
            week=week,
            data=data,
            model=model,
            voice=voice,
            snark_level=snark_level,
            hype_level=hype_level,
            focus_hints=focus_hints,
            focus_teams=focus_teams,
            favored_teams=favored_teams,
            disfavored_teams=disfavored_teams,
            bias_intensity=bias_intensity,
            length_target=length_target,
        )
    )


async def generate_with_config_async(
    config: ReportConfig,
    *,
    data: Optional[SleeperLeagueData] = None,
    model: str = "gpt-4o",
) -> ArticleOutput:
    """Generate a report using a pre-built ReportConfig.

    Use this when you want full control over the configuration.

    Args:
        config: The ReportConfig to use.
        data: Optional pre-loaded SleeperLeagueData.
        model: The model to use for generation.

    Returns:
        ArticleOutput containing the article, config, brief, and research log.
    """
    if data is None:
        data = SleeperLeagueData()
        data.load()

    agent = ReporterAgent(data, model=model)
    return await agent.run_with_config(config)


def generate_with_config(
    config: ReportConfig,
    *,
    data: Optional[SleeperLeagueData] = None,
    model: str = "gpt-4o",
) -> ArticleOutput:
    """Generate a report using a pre-built ReportConfig synchronously.

    See generate_with_config_async for full documentation.
    """
    return asyncio.run(
        generate_with_config_async(config, data=data, model=model)
    )


# Convenience functions for common use cases


async def weekly_recap_async(
    week: int,
    *,
    data: Optional[SleeperLeagueData] = None,
    model: str = "gpt-4o",
    snark_level: int = 1,
    hype_level: int = 2,
) -> ArticleOutput:
    """Generate a weekly recap article.

    Args:
        week: The week number to recap.
        data: Optional pre-loaded SleeperLeagueData.
        model: The model to use.
        snark_level: 0-3, how snarky.
        hype_level: 0-3, how hyped.

    Returns:
        ArticleOutput with the weekly recap.
    """
    return await generate_report_async(
        f"Write a comprehensive weekly recap for week {week}. "
        "Cover the major storylines, notable games, top performers, "
        "and any important transactions.",
        week=week,
        data=data,
        model=model,
        snark_level=snark_level,
        hype_level=hype_level,
        focus_hints=["matchups", "standings", "top performers"],
        length_target=1200,
    )


def weekly_recap(
    week: int,
    *,
    data: Optional[SleeperLeagueData] = None,
    model: str = "gpt-4o",
    snark_level: int = 1,
    hype_level: int = 2,
) -> ArticleOutput:
    """Generate a weekly recap article synchronously."""
    return asyncio.run(
        weekly_recap_async(
            week, data=data, model=model, snark_level=snark_level, hype_level=hype_level
        )
    )


async def snarky_recap_async(
    week: int,
    *,
    data: Optional[SleeperLeagueData] = None,
    model: str = "gpt-4o",
    disfavored_teams: Optional[list[str]] = None,
) -> ArticleOutput:
    """Generate a snarky weekly recap with roasting.

    Args:
        week: The week number to recap.
        data: Optional pre-loaded SleeperLeagueData.
        model: The model to use.
        disfavored_teams: Teams to roast particularly hard.

    Returns:
        ArticleOutput with the snarky recap.
    """
    request = f"Write a snarky, entertaining recap of week {week}. "
    "Be witty and don't hold back on teams that underperformed."

    if disfavored_teams:
        request += f" Give extra roasting attention to: {', '.join(disfavored_teams)}."

    return await generate_report_async(
        request,
        week=week,
        data=data,
        model=model,
        voice="snarky columnist",
        snark_level=3,
        hype_level=1,
        disfavored_teams=disfavored_teams,
        bias_intensity=3,
        length_target=1000,
    )


def snarky_recap(
    week: int,
    *,
    data: Optional[SleeperLeagueData] = None,
    model: str = "gpt-4o",
    disfavored_teams: Optional[list[str]] = None,
) -> ArticleOutput:
    """Generate a snarky weekly recap synchronously."""
    return asyncio.run(
        snarky_recap_async(week, data=data, model=model, disfavored_teams=disfavored_teams)
    )
