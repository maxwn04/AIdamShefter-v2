"""High-level workflow functions for reporter v2."""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import text

from datalayer.context_store import ContextStore
from datalayer.sleeper_data import SleeperLeagueData
from reporter_v2.config import BiasProfile, ReportConfig, TimeRange, ToneControls
from reporter_v2.runner.entrypoint import generate_article
from reporter_v2.runner.schemas import ArticleOutput


async def generate_report_async(
    request: str,
    *,
    week: int | None = None,
    data: SleeperLeagueData | None = None,
    model: str | None = "gpt-5-mini",
    voice: str = "sports columnist",
    snark_level: int = 1,
    hype_level: int = 1,
    focus_hints: list[str] | None = None,
    focus_teams: list[str] | None = None,
    favored_teams: list[str] | None = None,
    disfavored_teams: list[str] | None = None,
    bias_intensity: int = 2,
    length_target: int = 1000,
    context_store: ContextStore | None = None,
    data_dir: Path | str = Path(".data"),
    log_path: Path | None = None,
) -> ArticleOutput:
    """Generate a fantasy football report asynchronously."""
    data = _ensure_data(data)
    resolved_week = _resolve_week(data, week)

    config = ReportConfig(
        time_range=TimeRange.single_week(resolved_week),
        focus_hints=focus_hints or [],
        focus_teams=focus_teams or [],
        voice=voice,
        tone=ToneControls(snark_level=snark_level, hype_level=hype_level),
        bias_profile=_build_bias(favored_teams, disfavored_teams, bias_intensity),
        length_target=length_target,
        custom_instructions=request,
    )
    return await generate_with_config_async(
        config,
        data=data,
        model=model,
        context_store=context_store,
        data_dir=data_dir,
        log_path=log_path,
    )


def generate_report(
    request: str,
    **kwargs,
) -> ArticleOutput:
    """Generate a fantasy football report synchronously."""
    return asyncio.run(generate_report_async(request, **kwargs))


async def generate_with_config_async(
    config: ReportConfig,
    *,
    data: SleeperLeagueData | None = None,
    model: str | None = "gpt-5-mini",
    context_store: ContextStore | None = None,
    data_dir: Path | str = Path(".data"),
    log_path: Path | None = None,
) -> ArticleOutput:
    """Generate a report using a pre-built ReportConfig."""
    data = _ensure_data(data)
    context_store = context_store or _make_context_store(data, Path(data_dir))
    return await generate_article(
        data,
        config,
        context_store=context_store,
        model=model,
        log_path=log_path,
    )


def generate_with_config(
    config: ReportConfig,
    **kwargs,
) -> ArticleOutput:
    """Generate a report from a ReportConfig synchronously."""
    return asyncio.run(generate_with_config_async(config, **kwargs))


async def weekly_recap_async(
    week: int,
    *,
    data: SleeperLeagueData | None = None,
    model: str | None = "gpt-5-mini",
    snark_level: int = 1,
    hype_level: int = 2,
    **kwargs,
) -> ArticleOutput:
    """Generate a weekly recap article."""
    kwargs.setdefault("focus_hints", ["matchups", "standings", "top performers"])
    kwargs.setdefault("length_target", 1200)
    kwargs.setdefault("snark_level", snark_level)
    kwargs.setdefault("hype_level", hype_level)
    return await generate_report_async(
        f"Write a comprehensive weekly recap for week {week}. "
        "Cover the major storylines, notable games, top performers, "
        "and important transactions.",
        week=week,
        data=data,
        model=model,
        **kwargs,
    )


def weekly_recap(
    week: int,
    **kwargs,
) -> ArticleOutput:
    """Generate a weekly recap article synchronously."""
    return asyncio.run(weekly_recap_async(week, **kwargs))


async def snarky_recap_async(
    week: int,
    *,
    data: SleeperLeagueData | None = None,
    model: str | None = "gpt-5-mini",
    disfavored_teams: list[str] | None = None,
    **kwargs,
) -> ArticleOutput:
    """Generate a snarky weekly recap with roasting."""
    request = (
        f"Write a snarky, entertaining recap of week {week}. "
        "Be witty and do not hold back on teams that underperformed."
    )
    if disfavored_teams:
        request += f" Give extra roasting attention to: {', '.join(disfavored_teams)}."

    kwargs.setdefault("voice", "snarky columnist")
    kwargs.setdefault("snark_level", 3)
    kwargs.setdefault("hype_level", 1)
    kwargs.setdefault("disfavored_teams", disfavored_teams)
    kwargs.setdefault("bias_intensity", 3)
    kwargs.setdefault("length_target", 1000)
    return await generate_report_async(
        request,
        week=week,
        data=data,
        model=model,
        **kwargs,
    )


def snarky_recap(
    week: int,
    **kwargs,
) -> ArticleOutput:
    """Generate a snarky weekly recap synchronously."""
    return asyncio.run(snarky_recap_async(week, **kwargs))


def _ensure_data(data: SleeperLeagueData | None) -> SleeperLeagueData:
    if data is not None:
        return data
    loaded = SleeperLeagueData()
    loaded.load()
    return loaded


def _resolve_week(data: SleeperLeagueData, week: int | None) -> int:
    if week is not None:
        return week
    if data.effective_week is None:
        raise ValueError("Week must be provided when data.effective_week is unavailable.")
    return int(data.effective_week)


def _make_context_store(data: SleeperLeagueData, data_dir: Path) -> ContextStore:
    return ContextStore(
        db_path=data_dir / "context.db",
        league_id=data.league_id,
        season=_get_season(data),
    )


def _get_season(data: SleeperLeagueData) -> str:
    conn = getattr(data, "_query_conn", None)
    if conn is None:
        return ""
    row = conn.execute(text("SELECT season FROM leagues LIMIT 1")).first()
    return str(row[0]) if row else ""


def _build_bias(
    favored_teams: list[str] | None,
    disfavored_teams: list[str] | None,
    intensity: int,
) -> BiasProfile | None:
    if not favored_teams and not disfavored_teams:
        return None
    return BiasProfile(
        favored_teams=favored_teams or [],
        disfavored_teams=disfavored_teams or [],
        intensity=intensity,
    )
