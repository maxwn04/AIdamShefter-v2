from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.resources.memory.common.errors import GenerationMemoryContextClosedError
from backend.resources.memory.revisions import CanonicalRevision
from backend.resources.reporting.generations import (
    Generation,
    GenerationKind,
    GenerationLifecycleConflict,
    GenerationStatus,
)
from backend.services.datalayer import ReadyDataSnapshot, VerifiedLocalArtifact
from backend.services.generations import (
    GenerationRequest,
    GenerationService,
    GenerationSettings,
    ReconcileResult,
    RerunGenerationRequest,
    StaleGenerationPolicy,
)
from backend.services.memory import MemoryMutationResult
from backend.services.reporter import ReporterOutput
from backend.services.reporter.runner.completion import ProviderConfigurationError
from backend.services.reporter.runner.recording import ArtifactMutation
from backend.services.reporter.runner.schemas import ArtifactSnapshot


NOW = datetime(2026, 10, 29, 19, 30, tzinfo=UTC)


def _uuid(value: int) -> UUID:
    return UUID(int=value)


class FakeGenerationManager:
    def __init__(self, competition_id: UUID, events: list[str]) -> None:
        self.competition_id = competition_id
        self.events = events
        self.rows: dict[UUID, Generation] = {}
        self.starts = []
        self.start_error: Exception | None = None

    def create_pending(self, command):
        self.events.append("submit")
        row = _generation(
            generation_id=command.generation_id,
            competition_id=self.competition_id,
            season_id=command.competition_season_id,
            kind=command.kind,
            settings=command.settings,
            request_text=command.request_text,
            week_start=command.week_start,
            week_end=command.week_end,
            model=command.requested_primary_model,
            rerun_of_generation_id=command.rerun_of_generation_id,
        )
        self.rows[row.id] = row
        return row

    def get(self, generation_id):
        return self.rows[generation_id]

    def start(self, command):
        self.events.append("start")
        if self.start_error is not None:
            raise self.start_error
        self.starts.append(command)
        row = self.rows[command.generation_id]
        started = row.model_copy(
            update={
                "status": GenerationStatus.RUNNING,
                "data_snapshot_id": command.data_snapshot_id,
                "input_memory_revision_id": command.input_memory_revision_id,
                "knowledge_cutoff_at": command.knowledge_cutoff_at,
                "input_manifest": command.input_manifest,
                "manifest_schema_version": command.manifest_schema_version,
                "manifest_hash": command.manifest_hash,
                "current_stage": command.initial_stage,
                "progress_updated_at": NOW,
                "started_at": NOW,
            }
        )
        self.rows[row.id] = started
        return started

    def fail(self, command):
        self.events.append("fail")
        row = self.rows[command.generation_id]
        if command.expected_status is not None and row.status is not command.expected_status:
            raise GenerationLifecycleConflict(row.id, "status changed")
        failed = row.model_copy(
            update={
                "status": GenerationStatus.FAILED,
                "current_stage": "failed",
                "failure_category": command.category,
                "failure_summary": command.summary,
                "completed_at": NOW,
            }
        )
        self.rows[row.id] = failed
        return failed

    def cancel(self, command):
        self.events.append("cancel")
        row = self.rows[command.generation_id]
        if command.expected_status is not None and row.status is not command.expected_status:
            raise GenerationLifecycleConflict(row.id, "status changed")
        cancelled = row.model_copy(
            update={
                "status": GenerationStatus.CANCELLED,
                "current_stage": "cancelled",
                "failure_category": "cancelled",
                "failure_summary": command.summary,
                "completed_at": NOW,
            }
        )
        self.rows[row.id] = cancelled
        return cancelled

    def fail_stale_running(self, *, stale_before, limit):
        self.events.append("reconcile")
        stale = [
            row
            for row in self.rows.values()
            if row.status is GenerationStatus.RUNNING
            and row.progress_updated_at is not None
            and row.progress_updated_at < stale_before
        ][:limit]
        return tuple(
            self.fail(
                SimpleNamespace(
                    generation_id=row.id,
                    expected_status=GenerationStatus.RUNNING,
                    category="stale_execution",
                    summary="Generation execution became stale",
                )
            )
            for row in stale
        )


class FakeSnapshots:
    def __init__(self, snapshot: ReadyDataSnapshot, events: list[str]) -> None:
        self.snapshot = snapshot
        self.events = events
        self.requests = []
        self.error: Exception | None = None

    def get_or_create(self, request):
        self.events.append("snapshot")
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.snapshot


class FakeRevisions:
    def __init__(
        self,
        current: CanonicalRevision,
        history: tuple[CanonicalRevision, ...],
        events: list[str],
    ) -> None:
        self.current_revision = current
        self.revision_history = history
        self.events = events
        self.current_calls = 0
        self.history_calls = 0

    def current(self):
        self.events.append("memory")
        self.current_calls += 1
        return self.current_revision

    def ensure_current(self):
        self.events.append("memory")
        self.current_calls += 1
        return self.current_revision

    def history(self):
        self.events.append("memory")
        self.history_calls += 1
        return self.revision_history


class FakeFrozenData:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.closed = False

    def __enter__(self):
        self.events.append("open")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.events.append("close")
        self.closed = True

    def run_sql(self, query, *, limit=200):
        del query, limit
        return {"rows": [("league-1", "League One")]}


class FakeReporter:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls = []
        self.error: BaseException | None = None
        self.exercise_recorder = False
        self.finalizer = None

    async def __call__(self, data, config, **kwargs):
        self.events.append("reporter")
        self.calls.append((data, config, kwargs))
        if self.exercise_recorder:
            kwargs["recorder"].record_artifact_mutation(
                ArtifactMutation(
                    path="research_brief.md",
                    media_type="text/markdown",
                    content="brief",
                    revision=1,
                    content_hash=(
                        "1fc40f69be3cfdf6b1e1d7f4d880a67e"
                        "dcf44d16f501cf91e9f2877f733ed59f"
                    ),
                )
            )
        if self.error is not None:
            raise self.error
        content = "# Article"
        return ReporterOutput(
            submitted_path="article.md",
            artifacts=(
                ArtifactSnapshot(
                    path="article.md",
                    content=content,
                    revision=1,
                    content_hash=(
                        "1f4d9127a0b36fbb412b83e36f31f7b0"
                        "6665f13e8694015f0bb2e5cb04976bbe"
                    ),
                ),
            ),
        )


class FakeFinalizer:
    def __init__(self, manager, events):
        self.manager = manager
        self.events = events
        self.calls = []
        self.error: Exception | None = None

    def finalize(self, generation_id, output, memory_bundle):
        self.events.append("finalize")
        self.calls.append((generation_id, output, memory_bundle))
        if self.error is not None:
            raise self.error
        row = self.manager.rows[generation_id]
        succeeded = row.model_copy(
            update={
                "status": GenerationStatus.SUCCEEDED,
                "submitted_artifact_version_id": _uuid(500),
                "current_stage": "succeeded",
                "completed_at": NOW,
            }
        )
        self.manager.rows[generation_id] = succeeded
        memory_result = (
            MemoryMutationResult(revision=None, changes=())
            if row.kind is GenerationKind.LIVE
            else None
        )
        return SimpleNamespace(
            generation=succeeded,
            memory_result=memory_result,
        )


def _generation(
    *,
    generation_id: UUID,
    competition_id: UUID,
    season_id: UUID,
    kind: GenerationKind,
    settings: dict,
    request_text: str = "weekly recap",
    week_start: int | None = 7,
    week_end: int | None = 8,
    model: str = "gpt-test",
    rerun_of_generation_id: UUID | None = None,
) -> Generation:
    return Generation(
        id=generation_id,
        competition_id=competition_id,
        competition_season_id=season_id,
        data_snapshot_id=None,
        input_memory_revision_id=None,
        input_memory_artifact_version_id=None,
        input_memory_artifact_generation_id=None,
        evaluation_workspace_id=None,
        workspace_sequence_number=None,
        rerun_of_generation_id=rerun_of_generation_id,
        submitted_artifact_version_id=None,
        kind=kind,
        status=GenerationStatus.PENDING,
        request_text=request_text,
        week_start=week_start,
        week_end=week_end,
        domain_cutoff_week=None,
        domain_cutoff_at=None,
        knowledge_cutoff_at=None,
        requested_primary_model=model,
        settings=settings,
        input_manifest=None,
        manifest_schema_version=None,
        manifest_hash=None,
        current_turn=0,
        current_stage=None,
        progress_updated_at=None,
        failure_category=None,
        failure_summary=None,
        created_at=NOW,
        started_at=None,
        completed_at=None,
    )


def _revision(
    sequence: int,
    *,
    season_id: UUID | None,
    week: int | None,
    knowledge_cutoff_at: datetime | None = None,
) -> CanonicalRevision:
    return CanonicalRevision(
        revision_id=_uuid(100 + sequence),
        competition_id=_uuid(1),
        sequence_number=sequence,
        previous_revision_id=None if sequence == 0 else _uuid(99 + sequence),
        competition_season_id=season_id,
        week=week,
        knowledge_cutoff_at=knowledge_cutoff_at,
        state_content_hash=f"state-{sequence}",
        created_at=datetime(2026, 9, 1 + sequence, tzinfo=UTC),
    )


def _snapshot(tmp_path: Path) -> ReadyDataSnapshot:
    digest = "a" * 64
    return ReadyDataSnapshot(
        id=_uuid(20),
        competition_id=_uuid(1),
        primary_competition_season_id=_uuid(2),
        through_week=8,
        as_of_date=NOW.date(),
        build_key="build-key",
        snapshot_projection_version="snapshot-v2",
        artifact=VerifiedLocalArtifact(
            path=(tmp_path / "snapshot.sqlite").resolve(),
            storage_key=f"snapshots/sha256/aa/{digest}.sqlite",
            sha256=digest,
            byte_length=1,
        ),
    )


def _request(kind: GenerationKind = GenerationKind.LIVE) -> GenerationRequest:
    return GenerationRequest(
        generation_id=_uuid(3),
        competition_id=_uuid(1),
        competition_season_id=_uuid(2),
        kind=kind,
        request_text="weekly recap",
        week_start=7,
        week_end=8,
        requested_primary_model="gpt-test",
        settings=GenerationSettings(),
    )


def _service(
    tmp_path: Path,
    *,
    kind: GenerationKind = GenerationKind.LIVE,
    history: tuple[CanonicalRevision, ...] | None = None,
):
    events: list[str] = []
    manager = FakeGenerationManager(_uuid(1), events)
    snapshots = FakeSnapshots(_snapshot(tmp_path), events)
    root = _revision(0, season_id=None, week=None)
    revisions = FakeRevisions(
        root,
        history or (root,),
        events,
    )
    reporter = FakeReporter(events)
    finalizer = FakeFinalizer(manager, events)
    reporter.finalizer = finalizer
    runtime = FakeFrozenData(events)
    service = GenerationService(
        generations=manager,  # type: ignore[arg-type]
        snapshots=snapshots,
        revisions=revisions,  # type: ignore[arg-type]
        retrieval=SimpleNamespace(),  # type: ignore[arg-type]
        ai_calls=SimpleNamespace(),  # type: ignore[arg-type]
        tool_calls=SimpleNamespace(),  # type: ignore[arg-type]
        artifacts=SimpleNamespace(),  # type: ignore[arg-type]
        artifact_versions=SimpleNamespace(),  # type: ignore[arg-type]
        finalizer=finalizer,
        reporter_revision="reporter-10",
        generation_revision="generation-10",
        reporter=reporter,
        open_frozen_data=lambda snapshot: runtime,  # type: ignore[arg-type]
        clock=lambda: NOW,
    )
    service.submit(_request(kind))
    return service, manager, snapshots, revisions, reporter, runtime, events


def test_submit_resolves_and_persists_typed_settings(tmp_path) -> None:
    service, manager, _, _, _, _, events = _service(tmp_path)

    pending = manager.get(_uuid(3))

    assert pending.status is GenerationStatus.PENDING
    assert pending.settings["schema_version"] == 1
    assert pending.settings["input_policy"] == {
        "snapshot_refresh": "never",
        "snapshot_as_of_date": "execution_utc_date",
        "backtest_memory": "latest_same_season_at_or_before_week",
    }
    assert events == ["submit"]
    del service


def test_submit_rejects_cross_competition_scope(tmp_path) -> None:
    service, _, _, _, _, _, _ = _service(tmp_path)
    request = _request().model_copy(update={"competition_id": _uuid(99)})

    with pytest.raises(ValueError, match="outside the service competition"):
        service.submit(request)


@pytest.mark.asyncio
async def test_live_execution_pins_inputs_before_reporter_and_closes_runtime(
    tmp_path,
) -> None:
    service, manager, snapshots, revisions, reporter, runtime, events = _service(
        tmp_path
    )

    result = await service.execute(_uuid(3))

    assert events == [
        "submit",
        "snapshot",
        "memory",
        "start",
        "open",
        "reporter",
        "close",
        "finalize",
    ]
    assert snapshots.requests[0].through_week == 8
    assert snapshots.requests[0].as_of_date == NOW.date()
    assert revisions.current_calls == 1
    assert result.generation.status is GenerationStatus.SUCCEEDED
    assert result.memory_result == MemoryMutationResult(revision=None, changes=())
    bundle = reporter.finalizer.calls[0][2]
    assert bundle.expected_revision_id == _uuid(100)
    assert bundle.proposals == ()
    assert reporter.calls[0][2]["allow_memory_writes"] is True
    assert runtime.closed is True
    manifest = manager.starts[0].input_manifest
    assert manifest["cutoffs"]["domain_cutoff_at"] is None
    assert manifest["memory_input"]["revision_id"] == str(_uuid(100))
    procedure_versions = {
        entry["name"]: entry["version"]
        for entry in manifest["tools"]["implementations"]
    }
    assert procedure_versions["load_procedure"] == "3"


@pytest.mark.asyncio
async def test_backtest_selects_latest_same_season_revision_and_is_read_only(
    tmp_path,
) -> None:
    cutoff = datetime(2026, 10, 20, tzinfo=UTC)
    history = (
        _revision(4, season_id=_uuid(9), week=7),
        _revision(3, season_id=_uuid(2), week=9),
        _revision(2, season_id=_uuid(2), week=8, knowledge_cutoff_at=cutoff),
        _revision(1, season_id=_uuid(2), week=6),
        _revision(0, season_id=None, week=None),
    )
    service, manager, _, revisions, reporter, _, _ = _service(
        tmp_path,
        kind=GenerationKind.BACKTEST,
        history=history,
    )

    result = await service.execute(_uuid(3))

    assert revisions.current_calls == 1
    assert revisions.history_calls == 1
    assert manager.starts[0].input_memory_revision_id == _uuid(102)
    assert manager.starts[0].knowledge_cutoff_at == cutoff
    assert reporter.calls[0][2]["allow_memory_writes"] is False
    assert reporter.finalizer.calls[0][2].expected_revision_id == _uuid(102)
    assert result.memory_result is None


@pytest.mark.asyncio
async def test_backtest_falls_back_to_root_revision(tmp_path) -> None:
    history = (
        _revision(1, season_id=_uuid(2), week=9),
        _revision(0, season_id=None, week=None),
    )
    service, manager, _, _, _, _, _ = _service(
        tmp_path,
        kind=GenerationKind.BACKTEST,
        history=history,
    )

    await service.execute(_uuid(3))

    assert manager.starts[0].input_memory_revision_id == _uuid(100)
    assert manager.starts[0].knowledge_cutoff_at == history[1].created_at


@pytest.mark.asyncio
async def test_pre_start_failure_never_calls_reporter(tmp_path) -> None:
    service, manager, snapshots, _, reporter, runtime, events = _service(tmp_path)
    snapshots.error = RuntimeError("snapshot unavailable sk-secret-value")

    result = await service.execute(_uuid(3))

    assert "start" not in events
    assert reporter.calls == []
    assert runtime.closed is False
    assert result.generation.status is GenerationStatus.FAILED
    assert result.reporter_output is None
    assert result.generation.failure_category == "input_resolution"
    assert "secret" not in (result.generation.failure_summary or "")
    assert manager.get(_uuid(3)).status is GenerationStatus.FAILED


@pytest.mark.asyncio
async def test_atomic_start_failure_never_opens_runtime_or_calls_reporter(
    tmp_path,
) -> None:
    service, manager, _, _, reporter, runtime, events = _service(tmp_path)
    manager.start_error = RuntimeError("start rejected")

    result = await service.execute(_uuid(3))

    assert events[-1] == "fail"
    assert "open" not in events
    assert reporter.calls == []
    assert runtime.closed is False
    assert result.generation.status is GenerationStatus.FAILED


@pytest.mark.asyncio
async def test_non_pending_generation_is_not_executed(tmp_path) -> None:
    service, manager, snapshots, _, reporter, _, _ = _service(tmp_path)
    manager.rows[_uuid(3)] = manager.rows[_uuid(3)].model_copy(
        update={"status": GenerationStatus.FAILED}
    )

    with pytest.raises(GenerationLifecycleConflict, match="pending for execution"):
        await service.execute(_uuid(3))

    assert snapshots.requests == []
    assert reporter.calls == []


@pytest.mark.asyncio
async def test_backtest_without_eligible_or_root_memory_never_starts(tmp_path) -> None:
    history = (_revision(1, season_id=_uuid(2), week=9),)
    service, manager, _, _, reporter, _, _ = _service(
        tmp_path,
        kind=GenerationKind.BACKTEST,
        history=history,
    )

    result = await service.execute(_uuid(3))

    assert manager.starts == []
    assert reporter.calls == []
    assert result.generation.status is GenerationStatus.FAILED


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError("provider"), asyncio.CancelledError()])
async def test_reporter_failure_or_cancellation_closes_and_discards_context(
    tmp_path,
    error,
) -> None:
    service, manager, _, _, reporter, runtime, _ = _service(tmp_path)
    reporter.error = error

    result = await service.execute(_uuid(3))

    assert runtime.closed is True
    expected = (
        GenerationStatus.CANCELLED
        if isinstance(error, asyncio.CancelledError)
        else GenerationStatus.FAILED
    )
    assert result.generation.status is expected
    assert result.reporter_output is None
    assert manager.get(_uuid(3)).status is expected
    memory = reporter.calls[0][2]["memory_context"]
    with pytest.raises(GenerationMemoryContextClosedError):
        memory.take_completed_bundle()


@pytest.mark.asyncio
async def test_provider_configuration_failure_has_actionable_safe_summary(
    tmp_path,
) -> None:
    service, manager, _, _, reporter, runtime, _ = _service(tmp_path)
    reporter.error = ProviderConfigurationError()

    result = await service.execute(_uuid(3))

    assert runtime.closed is True
    assert result.generation.status is GenerationStatus.FAILED
    assert result.generation.failure_category == "reporter_execution"
    assert (
        result.generation.failure_summary
        == ProviderConfigurationError.public_summary
    )
    assert manager.get(_uuid(3)).failure_summary == (
        ProviderConfigurationError.public_summary
    )


@pytest.mark.asyncio
async def test_recorder_failure_closes_runtime_and_discards_context(tmp_path) -> None:
    service, manager, _, _, reporter, runtime, _ = _service(tmp_path)
    reporter.exercise_recorder = True

    result = await service.execute(_uuid(3))

    assert runtime.closed is True
    assert result.generation.status is GenerationStatus.FAILED
    assert manager.get(_uuid(3)).failure_category == "reporter_execution"
    memory = reporter.calls[0][2]["memory_context"]
    with pytest.raises(GenerationMemoryContextClosedError):
        memory.take_completed_bundle()


@pytest.mark.asyncio
async def test_finalization_failure_returns_failed_without_partial_output(tmp_path) -> None:
    service, manager, _, _, reporter, runtime, _ = _service(tmp_path)
    reporter.finalizer.error = RuntimeError("commit failed sk-secret-value")

    result = await service.execute(_uuid(3))

    assert runtime.closed is True
    assert result.generation.status is GenerationStatus.FAILED
    assert result.generation.failure_category == "generation_finalization"
    assert result.reporter_output is None
    assert "secret" not in (result.generation.failure_summary or "")
    assert manager.get(_uuid(3)).submitted_artifact_version_id is None


def test_rerun_copies_terminal_intent_and_links_fresh_pending_row(tmp_path) -> None:
    service, manager, _, _, _, _, _ = _service(tmp_path)
    manager.rows[_uuid(3)] = manager.rows[_uuid(3)].model_copy(
        update={"status": GenerationStatus.FAILED, "completed_at": NOW}
    )

    rerun = service.rerun(
        RerunGenerationRequest(
            source_generation_id=_uuid(3),
            generation_id=_uuid(4),
        )
    )

    assert rerun.status is GenerationStatus.PENDING
    assert rerun.rerun_of_generation_id == _uuid(3)
    assert rerun.request_text == manager.get(_uuid(3)).request_text
    assert rerun.settings == manager.get(_uuid(3)).settings
    assert rerun.data_snapshot_id is None
    assert manager.get(_uuid(3)).status is GenerationStatus.FAILED


def test_reconcile_stale_returns_only_bounded_running_rows(tmp_path) -> None:
    service, manager, _, _, _, _, _ = _service(tmp_path)
    manager.rows[_uuid(3)] = manager.rows[_uuid(3)].model_copy(
        update={
            "status": GenerationStatus.RUNNING,
            "progress_updated_at": NOW - timedelta(minutes=10),
        }
    )

    result = service.reconcile_stale(
        StaleGenerationPolicy(
            stale_before=NOW - timedelta(minutes=5),
            limit=1,
        )
    )

    assert isinstance(result, ReconcileResult)
    assert [row.id for row in result.generations] == [_uuid(3)]
    assert result.generations[0].failure_category == "stale_execution"


def test_request_rejects_duplicate_primary_and_fallback_model() -> None:
    settings = GenerationSettings.model_validate(
        {"model": {"fallback_models": ["gpt-test"]}}
    )

    with pytest.raises(ValueError, match="model chain"):
        GenerationRequest(
            generation_id=_uuid(3),
            competition_id=_uuid(1),
            competition_season_id=_uuid(2),
            kind=GenerationKind.LIVE,
            request_text="weekly recap",
            week_start=7,
            week_end=8,
            requested_primary_model="gpt-test",
            settings=settings,
        )
