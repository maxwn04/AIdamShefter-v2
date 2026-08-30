"""Generation-owned input resolution and reporter execution workflow."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import hashlib
from typing import Any, Protocol, cast
from uuid import UUID

from pydantic import JsonValue

from backend.resources.memory.revisions import CanonicalRevision, RevisionManager
from backend.resources.reporting.ai_calls import AICallManager
from backend.resources.reporting.artifact_versions import ArtifactVersionManager
from backend.resources.reporting.artifacts import ArtifactManager
from backend.resources.reporting.generations import (
    CancelGeneration,
    CreateGeneration,
    FailGeneration,
    Generation,
    GenerationKind,
    GenerationLifecycleConflict,
    GenerationManager,
    GenerationStatus,
    StartGeneration,
)
from backend.resources.reporting.memory_recalls import GenerationMemoryRecallManager
from backend.resources.reporting.tool_calls import ToolCallManager
from backend.services.datalayer import (
    DatalayerSnapshotService,
    FrozenLeagueData,
    ReadyDataSnapshot,
    SnapshotRequest,
)
from backend.services.generations.contracts import (
    GenerationExecutionResult,
    GenerationRequest,
    GenerationSettings,
    ReconcileResult,
    RerunGenerationRequest,
    StaleGenerationPolicy,
)
from backend.services.generations.finalization import GenerationFinalizationResult
from backend.services.generations.manifest import (
    BuiltGenerationManifest,
    CanonicalMemoryInput,
    CodeRevisionInput,
    DataSnapshotInput,
    GenerationManifestInput,
    GenerationRequestInput,
    ManifestCutoffs,
    ModelExecutionInput,
    ProcedureInput,
    RetryPolicyInput,
    RunnerExecutionInput,
    ToolInput,
    build_generation_manifest,
)
from backend.services.generations.recorder import GenerationExecutionRecorder
from backend.services.memory import (
    GenerationMemoryContext,
    MemoryMutationBundle,
    MemoryRetrievalService,
)
from backend.services.reporter import (
    BiasProfile,
    PreparedReporterDefinition,
    ProcedureHistoryMode,
    ReportConfig,
    ReporterOutput,
    RunnerConfig,
    TimeRange,
    ToneControls,
    generate_article,
    prepare_reporter_definition,
)
from backend.services.reporter.runner.completion import (
    CompletionSettings,
    ProviderConfigurationError,
    RetryPolicy,
)


GENERATION_SETTINGS_SCHEMA_VERSION = 1
SNAPSHOT_REFRESH_POLICY = "never"
BACKTEST_MEMORY_POLICY = "latest_same_season_at_or_before_week"

ReporterCallable = Callable[..., Awaitable[ReporterOutput]]
ReporterDefinitionFactory = Callable[..., PreparedReporterDefinition]
FrozenDataFactory = Callable[[ReadyDataSnapshot], FrozenLeagueData]
Clock = Callable[[], datetime]


class SnapshotResolver(Protocol):
    def get_or_create(self, request: SnapshotRequest) -> ReadyDataSnapshot: ...


class Finalizer(Protocol):
    def finalize(
        self,
        generation_id: UUID,
        output: ReporterOutput,
        memory_bundle: MemoryMutationBundle,
    ) -> GenerationFinalizationResult: ...


class GenerationService:
    """Submit durable requests and execute one fully pinned reporter run."""

    def __init__(
        self,
        *,
        generations: GenerationManager,
        snapshots: DatalayerSnapshotService | SnapshotResolver,
        revisions: RevisionManager,
        retrieval: MemoryRetrievalService,
        ai_calls: AICallManager,
        tool_calls: ToolCallManager,
        artifacts: ArtifactManager,
        artifact_versions: ArtifactVersionManager,
        finalizer: Finalizer,
        reporter_revision: str,
        generation_revision: str,
        memory_recalls: GenerationMemoryRecallManager | None = None,
        reporter: ReporterCallable = generate_article,
        prepare_definition: ReporterDefinitionFactory = prepare_reporter_definition,
        open_frozen_data: FrozenDataFactory = FrozenLeagueData.open,
        clock: Clock | None = None,
    ) -> None:
        self._generations = generations
        self._snapshots = snapshots
        self._revisions = revisions
        self._retrieval = retrieval
        self._ai_calls = ai_calls
        self._tool_calls = tool_calls
        self._artifacts = artifacts
        self._artifact_versions = artifact_versions
        self._memory_recalls = memory_recalls
        self._finalizer = finalizer
        self._reporter_revision = _nonblank(reporter_revision, "reporter_revision")
        self._generation_revision = _nonblank(
            generation_revision, "generation_revision"
        )
        self._reporter = reporter
        self._prepare_definition = prepare_definition
        self._open_frozen_data = open_frozen_data
        self._clock = clock or (lambda: datetime.now(UTC))

    def submit(self, request: GenerationRequest) -> Generation:
        """Persist one resolved pending generation without external work."""

        self._require_scope(request.competition_id)
        settings = _resolved_settings(request.settings)
        return self._generations.create_pending(
            CreateGeneration(
                generation_id=request.generation_id,
                competition_season_id=request.competition_season_id,
                kind=request.kind,
                request_text=request.request_text,
                week_start=request.week_start,
                week_end=request.week_end,
                requested_primary_model=request.requested_primary_model,
                settings=settings,
                rerun_of_generation_id=request.rerun_of_generation_id,
            )
        )

    async def execute(self, generation_id: UUID) -> GenerationExecutionResult:
        """Resolve, execute, and return one durably terminal generation."""

        pending = self._generations.get(generation_id)
        if pending.status is not GenerationStatus.PENDING:
            raise GenerationLifecycleConflict(
                pending.id,
                "generation must be pending for execution",
                expected_statuses=(GenerationStatus.PENDING.value,),
                actual_status=pending.status.value,
            )
        try:
            if pending.week_start is None or pending.week_end is None:
                raise ValueError("generation execution requires a resolved week range")
            execution_at = _aware_utc(self._clock())
            settings = _decode_settings(pending.settings)
            snapshot = self._snapshots.get_or_create(
                SnapshotRequest(
                    competition_season_id=pending.competition_season_id,
                    through_week=pending.week_end,
                    as_of_date=execution_at.date(),
                )
            )
            if (
                snapshot.competition_id != pending.competition_id
                or snapshot.primary_competition_season_id
                != pending.competition_season_id
                or snapshot.through_week != pending.week_end
            ):
                raise ValueError(
                    "resolved snapshot differs from generation scope or cutoff"
                )
            revision = self._select_memory_revision(pending)
            knowledge_cutoff_at = (
                execution_at
                if pending.kind is GenerationKind.LIVE
                else revision.knowledge_cutoff_at or revision.created_at
            )
            definition = self._prepare_definition(memory_enabled=True)
            manifest = _build_manifest(
                generation=pending,
                settings=settings,
                resolved_settings=pending.settings,
                snapshot=snapshot,
                revision=revision,
                knowledge_cutoff_at=knowledge_cutoff_at,
                definition=definition,
                reporter_revision=self._reporter_revision,
                generation_revision=self._generation_revision,
            )
        except asyncio.CancelledError:
            return self._cancel_result(pending.id, GenerationStatus.PENDING)
        except Exception as exc:
            return self._failure_result(
                pending.id,
                GenerationStatus.PENDING,
                "input_resolution",
                exc,
            )

        try:
            self._generations.start(
                StartGeneration(
                    generation_id=pending.id,
                    data_snapshot_id=snapshot.id,
                    input_memory_revision_id=revision.revision_id,
                    knowledge_cutoff_at=knowledge_cutoff_at,
                    input_manifest=manifest.manifest,
                    manifest_schema_version=manifest.schema_version,
                    manifest_hash=manifest.manifest_hash,
                    initial_stage="starting",
                )
            )
        except asyncio.CancelledError:
            return self._cancel_result(pending.id, GenerationStatus.PENDING)
        except GenerationLifecycleConflict:
            raise
        except Exception as exc:
            return self._failure_result(
                pending.id,
                GenerationStatus.PENDING,
                "input_resolution",
                exc,
            )

        memory = GenerationMemoryContext(
            competition_id=pending.competition_id,
            generation_id=pending.id,
            pinned_revision_id=revision.revision_id,
            retrieval=self._retrieval,
            competition_season_id=pending.competition_season_id,
            week=pending.week_end,
            knowledge_cutoff_at=knowledge_cutoff_at,
        )
        try:
            recorder = GenerationExecutionRecorder(
                pending.id,
                self._ai_calls,
                self._tool_calls,
                self._generations,
                self._artifacts,
                self._artifact_versions,
                self._memory_recalls,
            )
            with self._open_frozen_data(snapshot) as data:
                output = await self._reporter(
                    data,
                    _report_config(pending, settings),
                    memory_context=memory,
                    completion=_completion_settings(pending, settings),
                    runner_config=_runner_config(settings),
                    recorder=recorder,
                    allow_memory_writes=pending.kind is GenerationKind.LIVE,
                    automatic_memory_recall=settings.memory.automatic_recall,
                    definition=definition,
                )
            bundle = memory.take_completed_bundle()
        except asyncio.CancelledError:
            memory.discard()
            return self._cancel_result(pending.id, GenerationStatus.RUNNING)
        except Exception as exc:
            memory.discard()
            return self._failure_result(
                pending.id,
                GenerationStatus.RUNNING,
                "reporter_execution",
                exc,
            )
        except BaseException:
            memory.discard()
            raise

        try:
            finalized = self._finalizer.finalize(pending.id, output, bundle)
        except Exception as exc:
            return self._failure_result(
                pending.id,
                GenerationStatus.RUNNING,
                "generation_finalization",
                exc,
            )
        return GenerationExecutionResult(
            generation=finalized.generation,
            reporter_output=output,
            memory_result=finalized.memory_result,
        )

    def rerun(self, request: RerunGenerationRequest) -> Generation:
        """Copy one terminal generation's intent into a fresh linked request."""

        source = self._generations.get(request.source_generation_id)
        if source.status not in {
            GenerationStatus.SUCCEEDED,
            GenerationStatus.FAILED,
            GenerationStatus.CANCELLED,
        }:
            raise GenerationLifecycleConflict(
                source.id,
                "reruns require a terminal source generation",
                expected_statuses=("succeeded", "failed", "cancelled"),
                actual_status=source.status.value,
            )
        if source.week_start is None or source.week_end is None:
            raise ValueError("rerun source requires a resolved week range")
        return self.submit(
            GenerationRequest(
                generation_id=request.generation_id,
                competition_id=source.competition_id,
                competition_season_id=source.competition_season_id,
                kind=source.kind,
                request_text=source.request_text,
                week_start=source.week_start,
                week_end=source.week_end,
                requested_primary_model=source.requested_primary_model,
                settings=_decode_settings(source.settings),
                rerun_of_generation_id=source.id,
            )
        )

    def reconcile_stale(self, policy: StaleGenerationPolicy) -> ReconcileResult:
        """Fail a bounded batch of stale running generations without resuming them."""

        stale = self._generations.fail_stale_running(
            stale_before=policy.stale_before,
            limit=policy.limit,
        )
        return ReconcileResult(
            stale_before=policy.stale_before,
            generations=stale,
        )

    def _failure_result(
        self,
        generation_id: UUID,
        expected_status: GenerationStatus,
        category: str,
        exc: Exception,
    ) -> GenerationExecutionResult:
        try:
            generation = self._generations.fail(
                FailGeneration(
                    generation_id=generation_id,
                    category=category,
                    summary=_failure_summary(category, exc),
                    expected_status=expected_status,
                )
            )
        except GenerationLifecycleConflict:
            generation = self._generations.get(generation_id)
            if generation.status not in {
                GenerationStatus.FAILED,
                GenerationStatus.CANCELLED,
            }:
                raise
        return GenerationExecutionResult(generation=generation)

    def _cancel_result(
        self,
        generation_id: UUID,
        expected_status: GenerationStatus,
    ) -> GenerationExecutionResult:
        try:
            generation = self._generations.cancel(
                CancelGeneration(
                    generation_id=generation_id,
                    summary="Generation execution was cancelled",
                    expected_status=expected_status,
                )
            )
        except GenerationLifecycleConflict:
            generation = self._generations.get(generation_id)
            if generation.status not in {
                GenerationStatus.FAILED,
                GenerationStatus.CANCELLED,
            }:
                raise
        return GenerationExecutionResult(generation=generation)

    def _select_memory_revision(self, generation: Generation) -> CanonicalRevision:
        current = self._revisions.ensure_current()
        if generation.kind is GenerationKind.LIVE:
            return current
        if generation.week_end is None:
            raise ValueError("backtest memory selection requires a cutoff week")
        history = self._revisions.history()
        eligible = [
            revision
            for revision in history
            if revision.competition_season_id == generation.competition_season_id
            and revision.week is not None
            and revision.week <= generation.week_end
        ]
        if eligible:
            return max(eligible, key=lambda revision: revision.sequence_number)
        roots = [revision for revision in history if revision.sequence_number == 0]
        if not roots:
            raise ValueError("backtest memory selection requires a root revision")
        return roots[0]

    def _require_scope(self, competition_id: UUID) -> None:
        if competition_id != self._generations.competition_id:
            raise ValueError("generation request is outside the service competition")


def _resolved_settings(settings: GenerationSettings) -> dict[str, JsonValue]:
    resolved = cast(dict[str, JsonValue], settings.model_dump(mode="json"))
    return {
        "schema_version": GENERATION_SETTINGS_SCHEMA_VERSION,
        **resolved,
        "input_policy": {
            "snapshot_refresh": SNAPSHOT_REFRESH_POLICY,
            "snapshot_as_of_date": "execution_utc_date",
            "backtest_memory": BACKTEST_MEMORY_POLICY,
        },
    }


def _decode_settings(value: dict[str, JsonValue]) -> GenerationSettings:
    if value.get("schema_version") != GENERATION_SETTINGS_SCHEMA_VERSION:
        raise ValueError("generation settings schema version is unsupported")
    expected_policy = {
        "snapshot_refresh": SNAPSHOT_REFRESH_POLICY,
        "snapshot_as_of_date": "execution_utc_date",
        "backtest_memory": BACKTEST_MEMORY_POLICY,
    }
    if value.get("input_policy") != expected_policy:
        raise ValueError("generation input policy differs from the submitted policy")
    decoded = {key: value[key] for key in ("report", "model", "runner")}
    if "memory" in value:
        decoded["memory"] = value["memory"]
    return GenerationSettings.model_validate(decoded)


def _build_manifest(
    *,
    generation: Generation,
    settings: GenerationSettings,
    resolved_settings: dict[str, JsonValue],
    snapshot: ReadyDataSnapshot,
    revision: CanonicalRevision,
    knowledge_cutoff_at: datetime,
    definition: PreparedReporterDefinition,
    reporter_revision: str,
    generation_revision: str,
) -> BuiltGenerationManifest:
    if generation.week_end is None:
        raise ValueError("manifest construction requires a cutoff week")
    retry = settings.model.retry
    return build_generation_manifest(
        GenerationManifestInput(
            generation=GenerationRequestInput(
                kind=generation.kind,
                request_text=generation.request_text,
                resolved_settings=resolved_settings,
            ),
            data_snapshot=DataSnapshotInput(
                data_snapshot_id=snapshot.id,
                snapshot_projection_version=snapshot.snapshot_projection_version,
                artifact_sha256=snapshot.artifact.sha256,
            ),
            memory_input=CanonicalMemoryInput(revision_id=revision.revision_id),
            cutoffs=ManifestCutoffs(
                domain_cutoff_week=generation.week_end,
                domain_cutoff_at=None,
                knowledge_cutoff_at=knowledge_cutoff_at,
            ),
            model=ModelExecutionInput(
                requested_model=generation.requested_primary_model,
                fallback_models=settings.model.fallback_models,
                retry=RetryPolicyInput(
                    max_retries=retry.max_retries,
                    base_delay_seconds=retry.base_delay_seconds,
                    max_delay_seconds=retry.max_delay_seconds,
                ),
                request_parameters={},
            ),
            runner=RunnerExecutionInput(
                max_turns=settings.runner.max_turns,
                procedure_history_mode=settings.runner.procedure_history_mode,
            ),
            system_prompt_sha256=_content_sha256(definition.system_prompt),
            procedures=tuple(
                ProcedureInput(
                    name=procedure.name,
                    content_sha256=_content_sha256(procedure.content),
                )
                for procedure in definition.procedures
            ),
            tools=tuple(
                ToolInput(
                    name=tool.name,
                    definition=cast(dict[str, JsonValue], tool.definition),
                    implementation_version=tool.implementation_version,
                )
                for tool in definition.tools
            ),
            code=CodeRevisionInput(
                reporter_revision=reporter_revision,
                generation_revision=generation_revision,
            ),
        )
    )


def _report_config(
    generation: Generation,
    settings: GenerationSettings,
) -> ReportConfig:
    if generation.week_start is None or generation.week_end is None:
        raise ValueError("report configuration requires a week range")
    report = settings.report
    bias = report.bias
    return ReportConfig(
        time_range=TimeRange.range(generation.week_start, generation.week_end),
        focus_hints=list(report.focus_hints),
        avoid_topics=list(report.avoid_topics),
        focus_teams=list(report.focus_teams),
        voice=report.voice,
        tone=ToneControls(**report.tone.model_dump()),
        profanity_policy=report.profanity_policy,
        bias_profile=(
            BiasProfile(
                favored_teams=list(bias.favored_teams),
                disfavored_teams=list(bias.disfavored_teams),
                intensity=bias.intensity,
            )
            if bias is not None
            else None
        ),
        length_target=report.length_target,
        evidence_policy=report.evidence_policy,
        custom_instructions=generation.request_text,
    )


def _completion_settings(
    generation: Generation,
    settings: GenerationSettings,
) -> CompletionSettings:
    retry = settings.model.retry
    return CompletionSettings(
        model=generation.requested_primary_model,
        fallback_models=settings.model.fallback_models,
        retry=RetryPolicy(
            max_retries=retry.max_retries,
            base_delay=retry.base_delay_seconds,
            max_delay=retry.max_delay_seconds,
        ),
    )


def _runner_config(settings: GenerationSettings) -> RunnerConfig:
    return RunnerConfig(
        max_turns=settings.runner.max_turns,
        procedure_history_mode=ProcedureHistoryMode(
            settings.runner.procedure_history_mode
        ),
    )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("generation clock must return an aware datetime")
    return value.astimezone(UTC)


def _content_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _nonblank(value: str, field: str) -> str:
    if not value or value.strip() != value:
        raise ValueError(f"{field} must be non-blank and trimmed")
    return value


def _failure_summary(category: str, exc: Exception) -> str:
    if isinstance(exc, ProviderConfigurationError):
        return exc.public_summary[:500]
    label = category.replace("_", " ").capitalize()
    return f"{label} failed ({type(exc).__name__})"[:500]


__all__ = [
    "BACKTEST_MEMORY_POLICY",
    "GENERATION_SETTINGS_SCHEMA_VERSION",
    "GenerationService",
    "SNAPSHOT_REFRESH_POLICY",
]
