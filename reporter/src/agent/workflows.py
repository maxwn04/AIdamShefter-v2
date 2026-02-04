"""High-level workflow orchestration for article generation."""

from __future__ import annotations

import asyncio
from typing import Optional

from datalayer.sleeper_data import SleeperLeagueData

from agent.specs import ArticleRequest, ReportSpec
from agent.schemas import ArticleOutput
from agent.reporter_agent import ReporterAgent


async def run_article_request_async(
    request: ArticleRequest,
    data: Optional[SleeperLeagueData] = None,
    *,
    model: str = "gpt-4o",
) -> ArticleOutput:
    """Run the full article generation workflow asynchronously.

    Args:
        request: The article request to process.
        data: Optional pre-loaded SleeperLeagueData. If not provided,
              a new instance will be created and loaded.
        model: The model to use for generation.

    Returns:
        ArticleOutput containing the article, spec, brief, and metadata.
    """
    # Load data if not provided
    if data is None:
        data = SleeperLeagueData()
        data.load()

    # Create and run the agent
    agent = ReporterAgent(data, model=model)
    return await agent.run(request)


def run_article_request(
    request: ArticleRequest,
    data: Optional[SleeperLeagueData] = None,
    *,
    model: str = "gpt-4o",
) -> ArticleOutput:
    """Run the full article generation workflow synchronously.

    This is a convenience wrapper around run_article_request_async.

    Args:
        request: The article request to process.
        data: Optional pre-loaded SleeperLeagueData. If not provided,
              a new instance will be created and loaded.
        model: The model to use for generation.

    Returns:
        ArticleOutput containing the article, spec, brief, and metadata.
    """
    return asyncio.run(run_article_request_async(request, data, model=model))


async def generate_weekly_recap(
    week: int,
    data: Optional[SleeperLeagueData] = None,
    *,
    model: str = "gpt-4o",
    snark_level: int = 1,
    hype_level: int = 1,
    favored_teams: Optional[list[str]] = None,
    disfavored_teams: Optional[list[str]] = None,
    bias_intensity: int = 0,
) -> ArticleOutput:
    """Generate a weekly recap article.

    Convenience function for the most common use case.

    Args:
        week: The week number to recap.
        data: Optional pre-loaded SleeperLeagueData.
        model: The model to use for generation.
        snark_level: Snarkiness level (0-3).
        hype_level: Hype level (0-3).
        favored_teams: Teams to frame positively.
        disfavored_teams: Teams to frame negatively.
        bias_intensity: How strong the bias should be (0-3).

    Returns:
        ArticleOutput containing the article and metadata.
    """
    overrides = {
        "tone_controls": {
            "snark_level": snark_level,
            "hype_level": hype_level,
            "seriousness": 1,
        }
    }

    if favored_teams or disfavored_teams:
        overrides["bias_profile"] = {
            "favored_teams": favored_teams or [],
            "disfavored_teams": disfavored_teams or [],
            "intensity": bias_intensity,
        }

    request = ArticleRequest(
        raw_request=f"Weekly recap for week {week}",
        preset="weekly_recap",
        week=week,
        overrides=overrides,
    )

    return await run_article_request_async(request, data, model=model)


async def generate_power_rankings(
    week: int,
    data: Optional[SleeperLeagueData] = None,
    *,
    model: str = "gpt-4o",
) -> ArticleOutput:
    """Generate power rankings article.

    Args:
        week: The week to generate rankings for.
        data: Optional pre-loaded SleeperLeagueData.
        model: The model to use for generation.

    Returns:
        ArticleOutput containing the article and metadata.
    """
    request = ArticleRequest(
        raw_request=f"Power rankings after week {week}",
        preset="power_rankings",
        week=week,
    )

    return await run_article_request_async(request, data, model=model)


async def generate_team_deep_dive(
    team_name: str,
    week: int,
    data: Optional[SleeperLeagueData] = None,
    *,
    model: str = "gpt-4o",
) -> ArticleOutput:
    """Generate a team deep dive article.

    Args:
        team_name: The team to focus on.
        week: The current week for context.
        data: Optional pre-loaded SleeperLeagueData.
        model: The model to use for generation.

    Returns:
        ArticleOutput containing the article and metadata.
    """
    request = ArticleRequest(
        raw_request=f"Deep dive on {team_name}",
        preset="team_deep_dive",
        week=week,
        overrides={"focus_teams": [team_name]},
    )

    return await run_article_request_async(request, data, model=model)
