"""Composition root for platform reporter article generation.

Owns product wiring that the Runner must not know about:
- tool registration (artifacts, procedure, datalayer, memory)
- CompletionClient construction from settings / injectable fakes
- structured brief initialization from league data + ReportConfig
- system/user prompt construction
- typed memory capability wiring

The Runner receives a registry, client, RunnerConfig, artifact store, and
structured brief store.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from backend.services.reporter.config import ReportConfig
from backend.services.reporter.definition import (
    PreparedReporterDefinition,
    prepare_reporter_definition,
)
from backend.services.reporter.runner.completion import (
    CompletionClient,
    CompletionFn,
    CompletionSettings,
    make_completion_client,
)
from backend.services.reporter.runner.memory_closeout import MemoryCloseoutState
from backend.services.reporter.runner.recording import (
    ExecutionRecorder,
    MemoryRecallRecord,
)
from backend.services.reporter.runner.research_brief import (
    BriefBias,
    BriefContext,
    BriefStyle,
    ResearchBrief,
    ResearchBriefStore,
)
from backend.services.reporter.runner.runner import Runner
from backend.services.reporter.runner.schemas import ReporterOutput
from backend.services.reporter.runner.state import ArtifactStore, RunnerConfig
from backend.services.reporter.runner.tools.artifact_tools import register_artifact_tools
from backend.services.reporter.runner.tools.brief_tools import register_brief_tools
from backend.services.reporter.runner.tools.datalayer_tools import register_datalayer_tools
from backend.services.reporter.runner.tools.memory_closeout_tools import (
    register_memory_closeout_tools,
)
from backend.services.reporter.runner.tools.memory_tools import register_memory_tools
from backend.services.reporter.runner.tools.procedure_tools import register_procedure_tools
from backend.services.reporter.runner.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from backend.services.datalayer import FrozenLeagueData
    from backend.services.memory import GenerationMemoryContext
    from backend.services.reporter.runner.tools.memory_tools import TypedMemoryAdapter


async def generate_article(
    data: FrozenLeagueData,
    config: ReportConfig,
    *,
    memory_context: GenerationMemoryContext | None = None,
    client: CompletionClient | None = None,
    completion: CompletionSettings | None = None,
    runner_config: RunnerConfig | None = None,
    log_path: Path | None = None,
    complete: CompletionFn | None = None,
    recorder: ExecutionRecorder | None = None,
    allow_memory_writes: bool = True,
    automatic_memory_recall: bool = True,
    definition: PreparedReporterDefinition | None = None,
) -> ReporterOutput:
    """Generate an article with the single-loop v2 runner.

    Args:
        data: Already-open immutable league snapshot runtime.
        config: Article intent (weeks, voice, tone, bias, instructions).
        memory_context: Optional pinned typed memory; enables memory tools.
        client: Pre-built completion client. Mutually exclusive with complete=.
        completion: Settings used when constructing a client (or wrapping complete=).
        runner_config: Loop policy owned by Runner (max_turns, procedure mode).
        log_path: Optional streaming run-log path.
        complete: Injectable completion fn for tests. Mutually exclusive with client=.
        recorder: Optional generation-scoped durable execution recorder.
        allow_memory_writes: When False (eval mode), skip memory mutations
            while retaining pinned memory search.
        automatic_memory_recall: When False, retain memory tools and closeout
            while skipping the generation-start recall prelude.
    """
    prepared = definition or prepare_reporter_definition(
        memory_enabled=memory_context is not None
    )
    registry, memory_adapter = _build_registry(
        data,
        memory_context=memory_context,
        allow_memory_writes=allow_memory_writes,
        procedures=prepared.procedure_contents,
    )
    _require_matching_definition(registry, prepared)
    resolved_recorder = recorder
    if resolved_recorder is None and client is not None:
        resolved_recorder = cast(ExecutionRecorder | None, client.recorder)
    resolved_client = _resolve_client(
        client=client,
        completion=completion,
        complete=complete,
        recorder=resolved_recorder,
    )

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    league_id, league_name = _get_league_metadata(data)
    brief = ResearchBriefStore(
        brief=_build_research_brief(
            config,
            league_id=league_id,
            league_name=league_name,
        )
    )

    runner = Runner(
        registry,
        client=resolved_client,
        config=runner_config or RunnerConfig(),
        log_path=log_path,
        artifacts=ArtifactStore(),
        brief=brief,
        recorder=resolved_recorder,
        memory_closeout=(
            MemoryCloseoutState(
                procedure=prepared.procedure_contents["memory_closeout"],
                memory_writes_enabled=allow_memory_writes,
                proposal_snapshot=memory_context.proposal_snapshot,
            )
            if memory_context is not None
            else None
        ),
    )

    initial_context: tuple[str, ...] = ()
    if memory_adapter is not None and automatic_memory_recall:
        recall = memory_adapter.build_recall(config)
        if resolved_recorder is not None:
            record_recall = getattr(resolved_recorder, "record_memory_recall", None)
            if callable(record_recall):
                record_recall(
                    MemoryRecallRecord(
                        status=recall.status,
                        result=recall.result,
                        result_text=recall.result_text,
                        metadata=recall.metadata,
                    )
                )
        initial_context = (recall.result_text,)

    return await runner.run(
        prepared.system_prompt,
        _build_user_message(config),
        initial_context=initial_context,
    )


def _build_registry(
    data: FrozenLeagueData,
    *,
    memory_context: GenerationMemoryContext | None,
    allow_memory_writes: bool,
    procedures: dict[str, str] | None = None,
) -> tuple[ToolRegistry, TypedMemoryAdapter | None]:
    registry = ToolRegistry()
    memory_adapter = None
    register_artifact_tools(registry)
    register_brief_tools(registry)
    register_procedure_tools(registry, procedures)
    register_datalayer_tools(registry, data)
    if memory_context is not None:
        memory_adapter = register_memory_tools(
            registry,
            memory_context,
            data,
            allow_memory_writes=allow_memory_writes,
        )
        register_memory_closeout_tools(registry)
    return registry, memory_adapter


def _require_matching_definition(
    registry: ToolRegistry,
    definition: PreparedReporterDefinition,
) -> None:
    expected_specs = [tool.definition for tool in definition.tools]
    expected_versions = [
        (tool.name, tool.implementation_version) for tool in definition.tools
    ]
    if registry.tool_specs != expected_specs:
        raise ValueError("prepared reporter tool definitions differ from execution")
    if registry.tool_implementation_versions != expected_versions:
        raise ValueError("prepared reporter tool versions differ from execution")


def _resolve_client(
    *,
    client: CompletionClient | None,
    completion: CompletionSettings | None,
    complete: CompletionFn | None,
    recorder: ExecutionRecorder | None,
) -> CompletionClient:
    if client is not None and complete is not None:
        raise ValueError("Pass client= or complete=, not both.")
    if client is not None:
        if recorder is not None and client.recorder is not recorder:
            raise ValueError("A supplied client must already use the supplied recorder.")
        return client

    settings = completion or CompletionSettings()
    if complete is not None:
        return CompletionClient(complete, settings, recorder)
    return make_completion_client(settings, recorder)


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
            "Work on the unmet editorial goal that poses the greatest risk to "
            "accuracy or reader value. Treat the configured week range as current "
            "coverage; query outside it only for a specific relevant historical "
            "comparison and never beyond the frozen snapshot cutoff. Choose the "
            "smallest tool result that can resolve the current uncertainty. Load a "
            "procedure when its goal-oriented guidance would materially help, not "
            "as a fixed phase or progress marker.",
        ]
    )
    return "\n".join(lines)


def _build_research_brief(
    config: ReportConfig,
    *,
    league_id: str,
    league_name: str,
) -> ResearchBrief:
    """Build immutable request/style context for one structured brief."""
    bias = config.bias_profile
    return ResearchBrief(
        context=BriefContext(
            league_name=league_name,
            league_id=league_id,
            week_start=config.time_range.week_start,
            week_end=config.time_range.week_end,
            length_target=config.length_target,
            evidence_policy=config.evidence_policy,
            focus_hints=tuple(config.focus_hints),
            focus_teams=tuple(config.focus_teams),
            avoid_topics=tuple(config.avoid_topics),
            custom_instructions=config.custom_instructions.strip(),
        ),
        style=BriefStyle(
            voice=config.voice,
            snark_level=config.tone.snark_level,
            hype_level=config.tone.hype_level,
            seriousness=config.tone.seriousness,
            profanity_policy=config.profanity_policy,
        ),
        bias=BriefBias(
            favored_teams=tuple(bias.favored_teams if bias else ()),
            disfavored_teams=tuple(bias.disfavored_teams if bias else ()),
            intensity=bias.intensity if bias else 0,
        ),
    )


def _append_list(lines: list[str], label: str, values: list[str]) -> None:
    if values:
        lines.append(f"- {label}: {', '.join(values)}")


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
