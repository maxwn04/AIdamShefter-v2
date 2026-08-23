from datetime import UTC, datetime
from io import StringIO
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from backend.resources.reporting.generations import (
    Generation,
    GenerationKind,
    GenerationStatus,
)
from backend.services.generations import ReconcileResult
from backend.worker.main import run


NOW = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)


class StubRuntime:
    def __init__(self, readiness_error: Exception | None = None) -> None:
        self.readiness_error = readiness_error
        self.ready = False
        self.closed = False

    def assert_ready(self) -> None:
        self.ready = True
        if self.readiness_error is not None:
            raise self.readiness_error

    def close(self) -> None:
        self.closed = True


class StubService:
    def __init__(self, generation: Generation) -> None:
        self.generation = generation
        self.executed: list[UUID] = []
        self.policies: list[object] = []
        self.error: Exception | None = None

    async def execute(self, generation_id: UUID) -> object:
        self.executed.append(generation_id)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(generation=self.generation)

    def reconcile_stale(self, policy: object) -> ReconcileResult:
        self.policies.append(policy)
        if self.error is not None:
            raise self.error
        return ReconcileResult(
            stale_before=policy.stale_before,
            generations=(self.generation,),
        )


def _generation(status: GenerationStatus) -> Generation:
    succeeded = status is GenerationStatus.SUCCEEDED
    failed = status is GenerationStatus.FAILED
    return Generation(
        id=uuid4(),
        competition_id=uuid4(),
        competition_season_id=uuid4(),
        data_snapshot_id=uuid4(),
        input_memory_revision_id=uuid4(),
        input_memory_artifact_version_id=None,
        input_memory_artifact_generation_id=None,
        evaluation_workspace_id=None,
        workspace_sequence_number=None,
        rerun_of_generation_id=None,
        submitted_artifact_version_id=uuid4() if succeeded else None,
        kind=GenerationKind.LIVE,
        status=status,
        request_text="weekly recap",
        week_start=8,
        week_end=8,
        domain_cutoff_week=8,
        domain_cutoff_at=None,
        knowledge_cutoff_at=NOW,
        requested_primary_model="gpt-test",
        settings={"schema_version": 1},
        input_manifest={"schema_version": 1},
        manifest_schema_version=1,
        manifest_hash="a" * 64,
        current_turn=3,
        current_stage=status.value,
        progress_updated_at=NOW,
        failure_category="reporter_execution" if failed else None,
        failure_summary="Reporter execution failed (RuntimeError)" if failed else None,
        created_at=NOW,
        started_at=NOW,
        completed_at=NOW,
    )


@pytest.mark.parametrize(
    ("generation_status", "expected_exit"),
    [
        (GenerationStatus.SUCCEEDED, 0),
        (GenerationStatus.FAILED, 1),
        (GenerationStatus.CANCELLED, 1),
    ],
)
def test_execute_delegates_once_and_returns_bounded_terminal_output(
    generation_status: GenerationStatus,
    expected_exit: int,
) -> None:
    runtime = StubRuntime()
    generation = _generation(generation_status)
    service = StubService(generation)
    competition_id = uuid4()
    generation_id = uuid4()
    captured_competitions: list[UUID] = []
    stdout = StringIO()

    def dependencies(_runtime: object, scoped_competition_id: UUID) -> object:
        captured_competitions.append(scoped_competition_id)
        return SimpleNamespace(service=service)

    exit_code = run(
        [
            "execute",
            "--competition-id",
            str(competition_id),
            "--generation-id",
            str(generation_id),
        ],
        runtime_factory=lambda: runtime,
        dependency_factory=dependencies,  # type: ignore[arg-type]
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert exit_code == expected_exit
    assert runtime.ready is True
    assert runtime.closed is True
    assert captured_competitions == [competition_id]
    assert service.executed == [generation_id]
    assert payload["generation_id"] == str(generation.id)
    assert payload["status"] == generation_status.value
    assert set(payload) == {
        "generation_id",
        "status",
        "submitted_artifact_version_id",
        "failure_category",
        "failure_summary",
    }


def test_reconcile_stale_delegates_explicit_cutoff_and_limit() -> None:
    runtime = StubRuntime()
    service = StubService(_generation(GenerationStatus.FAILED))
    stdout = StringIO()

    exit_code = run(
        [
            "reconcile-stale",
            "--competition-id",
            str(uuid4()),
            "--stale-before",
            "2026-08-23T09:00:00Z",
            "--limit",
            "25",
        ],
        runtime_factory=lambda: runtime,
        dependency_factory=lambda *_args, **_kwargs: SimpleNamespace(
            service=service
        ),
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert service.policies[0].stale_before == datetime(
        2026, 8, 23, 9, 0, tzinfo=UTC
    )
    assert service.policies[0].limit == 25
    assert payload["count"] == 1
    assert runtime.closed is True


def test_worker_failures_are_sanitized_and_runtime_is_closed() -> None:
    runtime = StubRuntime()
    service = StubService(_generation(GenerationStatus.FAILED))
    service.error = RuntimeError("secret provider response")
    stderr = StringIO()

    exit_code = run(
        [
            "execute",
            "--competition-id",
            str(uuid4()),
            "--generation-id",
            str(uuid4()),
        ],
        runtime_factory=lambda: runtime,
        dependency_factory=lambda *_args, **_kwargs: SimpleNamespace(
            service=service
        ),
        stderr=stderr,
    )

    assert exit_code == 2
    assert stderr.getvalue() == "generation worker failed (RuntimeError)\n"
    assert "secret provider response" not in stderr.getvalue()
    assert runtime.closed is True


def test_readiness_failure_still_closes_runtime() -> None:
    runtime = StubRuntime(RuntimeError("database secret"))
    stderr = StringIO()

    exit_code = run(
        [
            "execute",
            "--competition-id",
            str(uuid4()),
            "--generation-id",
            str(uuid4()),
        ],
        runtime_factory=lambda: runtime,
        stderr=stderr,
    )

    assert exit_code == 2
    assert runtime.closed is True
    assert "database secret" not in stderr.getvalue()


def test_runtime_construction_failure_is_sanitized() -> None:
    stderr = StringIO()

    def fail_runtime() -> object:
        raise ValueError("secret database URL")

    exit_code = run(
        [
            "execute",
            "--competition-id",
            str(uuid4()),
            "--generation-id",
            str(uuid4()),
        ],
        runtime_factory=fail_runtime,  # type: ignore[arg-type]
        stderr=stderr,
    )

    assert exit_code == 2
    assert stderr.getvalue() == "generation worker failed (ValueError)\n"
    assert "secret database URL" not in stderr.getvalue()
