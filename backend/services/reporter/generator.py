"""Composition root for platform reporter article generation.

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

from backend.services.reporter.config import ReportConfig
from backend.services.reporter.runner.completion import (
    CompletionClient,
    CompletionFn,
    CompletionSettings,
    make_completion_client,
)
from backend.services.reporter.runner.memory_lifecycle import (
    finalize_memory_run,
    prepare_memory_run,
)
from backend.services.reporter.runner.runner import Runner
from backend.services.reporter.runner.schemas import ArticleOutput, BriefMeta, ReportBrief
from backend.services.reporter.runner.state import ArtifactStore, RunnerConfig
from backend.services.reporter.runner.tools.article_tools import register_article_tools
from backend.services.reporter.runner.tools.brief_tools import register_brief_tools
from backend.services.reporter.runner.tools.datalayer_tools import register_datalayer_tools
from backend.services.reporter.runner.tools.persistent_tools import register_persistent_tools
from backend.services.reporter.runner.tools.procedure_tools import register_procedure_tools
from backend.services.reporter.runner.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from backend.services.datalayer import FrozenLeagueData
    from reporter_memory.context_store import ContextStore


async def generate_article(
    data: FrozenLeagueData,
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
        data: Already-open immutable league snapshot runtime.
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

    league_id, league_name = _get_league_metadata(data)
    artifacts = ArtifactStore(
        brief=ReportBrief(
            meta=BriefMeta(
                league_id=league_id,
                league_name=league_name,
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
    data: FrozenLeagueData,
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
    path = Path(__file__).resolve().parent / "prompts" / "system.md"
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
    data: FrozenLeagueData,
) -> Callable[[str], dict[str, Any]]:
    def resolve(roster_key: str) -> dict[str, Any]:
        key = str(roster_key).strip()
        if not key:
            return {"found": False, "roster_key": roster_key}

        if key.isdigit():
            query = """
                SELECT r.roster_id, tp.team_name
                FROM rosters AS r
                LEFT JOIN team_profiles AS tp
                  ON tp.league_id = r.league_id
                 AND tp.roster_id = r.roster_id
                WHERE r.roster_id = :roster_id
            """
            params: dict[str, Any] = {"roster_id": int(key)}
        else:
            query = """
                SELECT roster_id, team_name
                FROM team_profiles
                WHERE (team_name IS NOT NULL AND lower(team_name) = lower(:key))
                   OR (manager_name IS NOT NULL AND lower(manager_name) = lower(:key))
                ORDER BY team_name ASC, manager_name ASC
            """
            params = {"key": key}

        try:
            result = data.run_sql(query, params, limit=2)
        except (RuntimeError, TypeError, ValueError):
            return {"found": False, "roster_key": roster_key}

        matches = [
            dict(zip(result.get("columns", ()), row, strict=True))
            for row in result.get("rows", ())
        ]
        if not matches:
            return {"found": False, "roster_key": roster_key}
        if len(matches) > 1:
            return {
                "found": False,
                "roster_key": roster_key,
                "matches": matches,
            }
        return {"found": True, **matches[0]}

    return resolve


def _get_league_metadata(data: FrozenLeagueData) -> tuple[str, str]:
    try:
        result = data.run_sql("SELECT league_id, name FROM leagues LIMIT 1", limit=1)
    except (RuntimeError, TypeError, ValueError):
        return "", ""
    rows = result.get("rows", ())
    if not rows:
        return "", ""
    league_id, league_name = rows[0]
    return str(league_id or ""), str(league_name or "")
