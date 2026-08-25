"""Composition root for platform reporter article generation.

Owns product wiring that the Runner must not know about:
- tool registration (artifacts, procedure, datalayer, memory)
- CompletionClient construction from settings / injectable fakes
- Markdown brief seeding from league data + ReportConfig
- system/user prompt construction
- typed memory capability wiring

The Runner only receives a registry, client, RunnerConfig, and optional
pre-seeded ArtifactStore.
"""

from __future__ import annotations

from collections.abc import Callable
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
from backend.services.reporter.runner.recording import (
    ArtifactMutation,
    ArtifactRecordingError,
    ExecutionRecorder,
)
from backend.services.reporter.runner.runner import Runner
from backend.services.reporter.runner.schemas import ArtifactSnapshot, ReporterOutput
from backend.services.reporter.runner.state import ArtifactStore, RunnerConfig
from backend.services.reporter.runner.tools.artifact_tools import register_artifact_tools
from backend.services.reporter.runner.tools.datalayer_tools import register_datalayer_tools
from backend.services.reporter.runner.tools.memory_tools import register_memory_tools
from backend.services.reporter.runner.tools.procedure_tools import register_procedure_tools
from backend.services.reporter.runner.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from backend.services.datalayer import FrozenLeagueData
    from backend.services.memory import GenerationMemoryContext


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
    """
    prepared = definition or prepare_reporter_definition(
        memory_enabled=memory_context is not None
    )
    registry = _build_registry(
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
    artifacts = ArtifactStore()
    artifacts.create(
        "research/brief.md",
        _build_brief_seed(
            config,
            league_id=league_id,
            league_name=league_name,
        ),
        on_change=(
            _seed_artifact_recorder(resolved_recorder)
            if resolved_recorder is not None
            else None
        ),
    )

    runner = Runner(
        registry,
        client=resolved_client,
        config=runner_config or RunnerConfig(),
        log_path=log_path,
        artifacts=artifacts,
        recorder=resolved_recorder,
    )

    return await runner.run(prepared.system_prompt, _build_user_message(config))


def _seed_artifact_recorder(
    recorder: ExecutionRecorder,
) -> Callable[[ArtifactSnapshot], None]:
    def record(snapshot: ArtifactSnapshot) -> None:
        try:
            recorder.record_artifact_mutation(
                ArtifactMutation(
                    path=snapshot.path,
                    media_type=snapshot.media_type,
                    content=snapshot.content,
                    revision=snapshot.revision,
                    content_hash=snapshot.content_hash,
                )
            )
        except Exception as exc:
            raise ArtifactRecordingError(
                f"Could not record seeded artifact {snapshot.path}"
            ) from exc

    return record


def _build_registry(
    data: FrozenLeagueData,
    *,
    memory_context: GenerationMemoryContext | None,
    allow_memory_writes: bool,
    procedures: dict[str, str] | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    register_artifact_tools(registry)
    register_procedure_tools(registry, procedures)
    register_datalayer_tools(registry, data)
    if memory_context is not None:
        register_memory_tools(
            registry,
            memory_context,
            data,
            allow_memory_writes=allow_memory_writes,
        )
    return registry


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
            "Begin with the action that will reduce the most important uncertainty. "
            "A broad league-data call is often useful, and the `research` procedure "
            "is available when its detailed checklist would help. Treat research, "
            "storyline mining, drafting, and verification as interleavable activities; "
            "do not load the four procedures as a fixed sequence.",
        ]
    )
    return "\n".join(lines)


def _build_brief_seed(
    config: ReportConfig,
    *,
    league_id: str,
    league_name: str,
) -> str:
    """Create the raw Markdown workspace document used throughout a run."""
    bias = config.bias_profile
    lines = [
        "# Research Brief",
        "",
        "## Context",
        "",
        f"- League: {league_name or '(unknown)'}",
        f"- League ID: {league_id or '(unknown)'}",
        (
            "- Coverage weeks: "
            f"{config.time_range.week_start}-{config.time_range.week_end}"
        ),
        f"- Target length: about {config.length_target} words",
        f"- Evidence policy: {config.evidence_policy}",
        "",
        "## Request",
        "",
        f"- Focus hints: {_markdown_list_value(config.focus_hints)}",
        f"- Focus teams: {_markdown_list_value(config.focus_teams)}",
        f"- Avoid topics: {_markdown_list_value(config.avoid_topics)}",
        (
            "- Custom instructions: "
            f"{config.custom_instructions.strip() or '(none)'}"
        ),
        "",
        "## Style and Bias",
        "",
        f"- Voice: {config.voice}",
        f"- Snark level: {config.tone.snark_level}",
        f"- Hype level: {config.tone.hype_level}",
        f"- Seriousness: {config.tone.seriousness}",
        f"- Profanity policy: {config.profanity_policy}",
        (
            "- Favored teams: "
            f"{_markdown_list_value(bias.favored_teams if bias else [])}"
        ),
        (
            "- Disfavored teams: "
            f"{_markdown_list_value(bias.disfavored_teams if bias else [])}"
        ),
        f"- Bias intensity: {bias.intensity if bias else 0}",
        "- Bias rule: framing only; never change facts.",
        "",
        "## Verified Facts",
        "",
        "<!-- INSERT VERIFIED FACTS ABOVE THIS LINE -->",
        "",
        "## Verified Callbacks",
        "",
        "<!-- INSERT VERIFIED CALLBACKS ABOVE THIS LINE -->",
        "",
        "## Storylines",
        "",
        "<!-- INSERT STORYLINES ABOVE THIS LINE -->",
        "",
        "## Outline",
        "",
        "<!-- INSERT OUTLINE ABOVE THIS LINE -->",
        "",
    ]
    return "\n".join(lines)


def _markdown_list_value(values: list[str]) -> str:
    return ", ".join(values) if values else "(none)"


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
