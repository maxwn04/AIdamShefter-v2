"""Entrypoint for reporter v2 article generation."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from datalayer.sleeper_data import SleeperLeagueData
from datalayer.sleeper_data.queries._resolvers import resolve_roster_id
from reporter_v2.config import ReportConfig
from reporter_v2.runner.runner import CompletionFn, Runner
from reporter_v2.runner.schemas import ArticleOutput
from reporter_v2.runner.state import RunnerConfig
from reporter_v2.runner.tools.article_tools import register_article_tools
from reporter_v2.runner.tools.brief_tools import register_brief_tools
from reporter_v2.runner.tools.datalayer_tools import register_datalayer_tools
from reporter_v2.runner.tools.persistent_tools import register_persistent_tools
from reporter_v2.runner.tools.procedure_tools import register_procedure_tools
from reporter_v2.runner.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from datalayer.context_store import ContextStore


async def generate_article(
    data: SleeperLeagueData,
    config: ReportConfig,
    *,
    context_store: ContextStore | None = None,
    model: str | None = None,
    log_path: Path | None = None,
    complete: CompletionFn | None = None,
) -> ArticleOutput:
    """Generate an article with the single-loop v2 runner."""
    week = config.time_range.week_end
    if context_store is not None:
        context_store.mark_stale(week)

    registry = ToolRegistry()
    register_brief_tools(registry)
    register_article_tools(registry)
    register_procedure_tools(registry)
    register_datalayer_tools(registry, data)
    if context_store is not None:
        register_persistent_tools(
            registry,
            context_store,
            week=week,
            resolve_roster_fn=_make_roster_resolver(data),
        )

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    runner = Runner(
        registry,
        complete=complete,
        config=RunnerConfig(model=model),
        log_path=log_path,
    )
    runner.artifacts.brief.meta.league_id = str(data.league_id)
    runner.artifacts.brief.meta.league_name = _get_league_name(data)
    runner.artifacts.brief.meta.week_start = config.time_range.week_start
    runner.artifacts.brief.meta.week_end = config.time_range.week_end

    return await runner.run(_build_system_prompt(), _build_user_message(config))


def _build_system_prompt() -> str:
    path = Path(__file__).resolve().parents[1] / "prompts" / "system.md"
    return path.read_text(encoding="utf-8").strip()


def _build_user_message(config: ReportConfig) -> str:
    lines = [
        "Generate a fantasy football article with these requirements.",
        "",
        "Coverage:",
        f"- Weeks: {config.time_range.week_start}-{config.time_range.week_end}",
        f"- Target length: about {config.length_target} words",
        f"- Evidence policy: {config.evidence_policy}",
        "",
        "Voice and tone:",
        f"- Voice: {config.voice}",
        f"- Snark level: {config.tone.snark_level}",
        f"- Hype level: {config.tone.hype_level}",
        f"- Seriousness: {config.tone.seriousness}",
        f"- Profanity policy: {config.profanity_policy}",
    ]

    _append_list(lines, "Focus hints", config.focus_hints)
    _append_list(lines, "Focus teams", config.focus_teams)
    _append_list(lines, "Avoid topics", config.avoid_topics)

    bias_instructions = config.get_bias_instructions()
    if bias_instructions:
        lines.extend(["", bias_instructions])

    if config.custom_instructions.strip():
        lines.extend(["", "Custom instructions:", config.custom_instructions.strip()])

    lines.extend(
        [
            "",
            "Start by loading the `research` procedure. Build the brief as you go, "
            "then use the storyline, drafting, and verification procedures as needed.",
        ]
    )
    return "\n".join(lines)


def _append_list(lines: list[str], label: str, values: list[str]) -> None:
    if values:
        lines.append(f"- {label}: {', '.join(values)}")


def _make_roster_resolver(
    data: SleeperLeagueData,
) -> Callable[[str], dict[str, Any]]:
    def resolve(roster_key: str) -> dict[str, Any]:
        conn = getattr(data, "_query_conn", None)
        if conn is None:
            return {"found": False, "roster_key": roster_key}
        return resolve_roster_id(conn, data.league_id, roster_key)

    return resolve


def _get_league_name(data: SleeperLeagueData) -> str:
    conn = getattr(data, "_query_conn", None)
    if conn is None:
        return ""

    try:
        row = conn.execute(text("SELECT name FROM leagues LIMIT 1")).first()
    except Exception:
        return ""
    if row is None:
        return ""
    return str(row[0] or "")
