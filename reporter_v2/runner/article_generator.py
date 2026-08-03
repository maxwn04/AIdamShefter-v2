"""Composition root for reporter v2 article generation.

Owns product wiring that the Runner must not know about:
- tool registration (brief, article, procedure, datalayer, memory)
- CompletionClient construction from settings / injectable fakes
- brief meta seeding from league data + ReportConfig
- system/user prompt construction
- memory run lifecycle (mark_stale / persist-on-submit via memory_lifecycle)

The Runner only receives a registry, client, RunnerConfig, and optional
pre-seeded ArtifactStore.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from datalayer.sleeper_data import SleeperLeagueData
from datalayer.sleeper_data.queries._resolvers import resolve_roster_id
from reporter_v2.config import ReportConfig
from reporter_v2.runner.completion import (
    CompletionClient,
    CompletionFn,
    CompletionSettings,
    make_completion_client,
)
from reporter_v2.runner.memory_lifecycle import (
    finalize_memory_run,
    prepare_memory_run,
)
from reporter_v2.runner.runner import Runner
from reporter_v2.runner.schemas import ArticleOutput, BriefMeta, ReportBrief
from reporter_v2.runner.state import ArtifactStore, RunnerConfig
from reporter_v2.runner.tools.article_tools import register_article_tools
from reporter_v2.runner.tools.brief_tools import register_brief_tools
from reporter_v2.runner.tools.datalayer_tools import register_datalayer_tools
from reporter_v2.runner.tools.persistent_tools import register_persistent_tools
from reporter_v2.runner.tools.procedure_tools import register_procedure_tools
from reporter_v2.runner.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from reporter_memory.context_store import ContextStore


async def generate_article(
    data: SleeperLeagueData,
    config: ReportConfig,
    *,
    context_store: ContextStore | None = None,
    client: CompletionClient | None = None,
    completion: CompletionSettings | None = None,
    runner_config: RunnerConfig | None = None,
    log_path: Path | None = None,
    complete: CompletionFn | None = None,
    allow_memory_writes: bool = True,
) -> ArticleOutput:
    """Generate an article with the single-loop v2 runner.

    Args:
        data: Loaded league data facade.
        config: Article intent (weeks, voice, tone, bias, instructions).
        context_store: Optional persistent memory; enables memory tools.
        client: Pre-built completion client. Mutually exclusive with complete=.
        completion: Settings used when constructing a client (or wrapping complete=).
        runner_config: Loop policy owned by Runner (max_turns, procedure mode).
        log_path: Optional streaming run-log path.
        complete: Injectable completion fn for tests. Mutually exclusive with client=.
        allow_memory_writes: When False (eval mode), skip memory mutations
            (lifecycle + in-run memory tools).
    """
    week = config.time_range.week_end
    prepare_memory_run(
        context_store,
        week=week,
        allow_writes=allow_memory_writes,
    )

    registry = _build_registry(
        data,
        context_store=context_store,
        week=week,
        allow_memory_writes=allow_memory_writes,
    )
    resolved_client = _resolve_client(
        client=client,
        completion=completion,
        complete=complete,
    )

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    artifacts = ArtifactStore(
        brief=ReportBrief(
            meta=BriefMeta(
                league_id=str(data.league_id),
                league_name=_get_league_name(data),
                week_start=config.time_range.week_start,
                week_end=config.time_range.week_end,
            )
        )
    )

    runner = Runner(
        registry,
        client=resolved_client,
        config=runner_config or RunnerConfig(),
        log_path=log_path,
        artifacts=artifacts,
    )

    output = await runner.run(_build_system_prompt(), _build_user_message(config))
    finalize_memory_run(
        context_store,
        output,
        week=week,
        allow_writes=allow_memory_writes,
    )
    return output


def _build_registry(
    data: SleeperLeagueData,
    *,
    context_store: ContextStore | None,
    week: int,
    allow_memory_writes: bool,
) -> ToolRegistry:
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
            allow_memory_writes=allow_memory_writes,
        )
    return registry


def _resolve_client(
    *,
    client: CompletionClient | None,
    completion: CompletionSettings | None,
    complete: CompletionFn | None,
) -> CompletionClient:
    if client is not None and complete is not None:
        raise ValueError("Pass client= or complete=, not both.")
    if client is not None:
        return client

    settings = completion or CompletionSettings()
    if complete is not None:
        return CompletionClient(complete, settings)
    return make_completion_client(settings)


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
