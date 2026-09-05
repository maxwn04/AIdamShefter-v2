from __future__ import annotations

from datetime import timedelta
import stat
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.resources.reporting.generations import GenerationKind, GenerationStatus
from backend.services.datalayer.contracts import SnapshotStatus
from backend.services.datalayer import FrozenLeagueData
from backend.services.datalayer.local_files import (
    LocalArtifactVerificationError,
    LocalDatalayerFileStore,
)
from backend.services.datalayer.snapshot_sqlite import SnapshotArtifactInvalid
from backend.services.generations import (
    GenerationSettings,
    PreparedGenerationExecution,
    PreparedSnapshotResolver,
)
from backend.tests.services.datalayer.test_resolved_snapshot_builder import _builder, _inputs
from backend.tests.services.generations.test_service import (
    NOW,
    _request,
    _service,
    _snapshot,
    _uuid,
)


def _execution(snapshot, *, revision_id=UUID(int=100)) -> PreparedGenerationExecution:
    return PreparedGenerationExecution(
        data_snapshot_id=snapshot.id,
        artifact_sha256=snapshot.artifact.sha256,
        input_revision=snapshot.input_revision,
        expected_memory_revision_id=revision_id,
        editorial_cutoff_at=NOW - timedelta(days=365),
    )


@pytest.mark.asyncio
async def test_prepared_execution_keeps_actual_knowledge_and_simulated_editorial_time(tmp_path):
    settings = GenerationSettings(prepared_execution=_execution(_snapshot(tmp_path)))
    service, manager, snapshots, revisions, reporter, _, _ = _service(tmp_path, settings=settings)
    # Exact snapshot resolver is the only injected read capability reached.
    service._prepared_snapshots = SimpleNamespace(resolve=lambda *args, **kwargs: snapshots.snapshot)
    result = await service.execute(_uuid(3))

    assert result.generation.status is GenerationStatus.SUCCEEDED
    assert not snapshots.preparation_requests and not snapshots.legacy_requests
    assert manager.starts[0].input_memory_revision_id == revisions.current_revision.revision_id
    assert manager.starts[0].knowledge_cutoff_at == NOW
    assert manager.starts[0].manifest_schema_version == 3
    cutoffs = manager.starts[0].input_manifest["cutoffs"]
    assert cutoffs["knowledge_cutoff_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert cutoffs["editorial_cutoff_at"] == settings.prepared_execution.editorial_cutoff_at.isoformat().replace("+00:00", "Z")
    _, config, kwargs = reporter.calls[0]
    assert kwargs["allow_memory_writes"] is True
    assert kwargs["memory_context"].knowledge_cutoff_at == NOW
    assert kwargs["memory_context"].editorial_cutoff_at == settings.prepared_execution.editorial_cutoff_at
    assert "Simulated reporting boundary:" in config.custom_instructions
    assert "retrospective factual inputs" in config.custom_instructions


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing_resolver", "wrong_head", "future_cutoff", "missing_snapshot"])
async def test_prepared_failures_never_fetch_start_or_call_reporter(tmp_path, failure):
    execution = _execution(_snapshot(tmp_path))
    if failure == "wrong_head":
        execution = execution.model_copy(update={"expected_memory_revision_id": _uuid(999)})
    if failure == "future_cutoff":
        execution = execution.model_copy(update={"editorial_cutoff_at": NOW + timedelta(seconds=1)})
    service, manager, snapshots, _, reporter, _, _ = _service(
        tmp_path, settings=GenerationSettings(prepared_execution=execution)
    )
    def resolve(*args, **kwargs):
        if failure == "missing_snapshot":
            raise FileNotFoundError("prepared input missing")
        return snapshots.snapshot
    if failure != "missing_resolver":
        service._prepared_snapshots = SimpleNamespace(resolve=resolve)
    result = await service.execute(_uuid(3))

    assert result.generation.status is GenerationStatus.FAILED
    assert result.generation.failure_category == "input_resolution"
    assert not snapshots.preparation_requests and not snapshots.legacy_requests
    assert not manager.starts and not reporter.calls


def test_prepared_policy_requires_live_and_aware_editorial_clock(tmp_path):
    execution = _execution(_snapshot(tmp_path))
    request = _request(GenerationKind.BACKTEST).model_dump()
    request["settings"] = GenerationSettings(prepared_execution=execution)
    with pytest.raises(ValueError, match="memory-writing live"):
        type(_request()).model_validate(request)
    with pytest.raises(ValueError, match="timezone"):
        PreparedGenerationExecution.model_validate({**execution.model_dump(), "editorial_cutoff_at": NOW.replace(tzinfo=None)})


def _sealed_resolver(tmp_path):
    inputs, candidates = _inputs()
    builder, snapshots, requests = _builder(tmp_path, inputs, candidates)
    ready = builder.get_or_create(inputs)
    requests.calls.clear()
    return PreparedSnapshotResolver(snapshots=snapshots, files=LocalDatalayerFileStore(tmp_path / "data")), snapshots, requests, ready


def _resolve(resolver, ready, execution=None):
    return resolver.resolve(
        execution or _execution(ready),
        competition_id=ready.competition_id,
        competition_season_id=ready.primary_competition_season_id,
        through_week=ready.through_week,
    )


def test_exact_prepared_resolver_reopens_real_sealed_sqlite_without_source_reads(tmp_path):
    resolver, snapshots, requests, ready = _sealed_resolver(tmp_path)
    resolved = _resolve(resolver, ready)
    assert resolved == ready
    assert not requests.calls
    assert len(snapshots.commands) == 1
    assert not snapshots.expired
    with FrozenLeagueData.open(resolved) as data:
        primary = resolved.included_seasons[-1]
        with pytest.raises(ValueError, match="1 through 3"):
            data.get_week_games(week=4, season=primary.season_year)
        assert data.get_week_games(week=3, season=primary.season_year) == []


@pytest.mark.parametrize("field,value", [
    ("competition_id", UUID(int=999)),
    ("primary_competition_season_id", UUID(int=999)),
    ("through_week", 4),
    ("input_revision", "d" * 64),
    ("status", SnapshotStatus.EXPIRED),
])
def test_exact_prepared_resolver_rejects_wrong_scope_or_identity(tmp_path, field, value):
    resolver, snapshots, requests, ready = _sealed_resolver(tmp_path)
    snapshots.current = snapshots.current.model_copy(update={field: value})
    with pytest.raises(ValueError, match="prepared snapshot"):
        _resolve(resolver, ready)
    assert not requests.calls and not snapshots.expired


def test_exact_prepared_resolver_rejects_wrong_pinned_hash(tmp_path):
    resolver, _, requests, ready = _sealed_resolver(tmp_path)
    execution = _execution(ready).model_copy(update={"artifact_sha256": "e" * 64})
    with pytest.raises(ValueError, match="pinned scope or identity"):
        _resolve(resolver, ready, execution)
    assert not requests.calls


@pytest.mark.parametrize("damage", ["missing", "corrupt", "membership"])
def test_exact_prepared_resolver_fails_closed_without_expire_or_rebuild(tmp_path, damage):
    resolver, snapshots, requests, ready = _sealed_resolver(tmp_path)
    if damage in {"missing", "corrupt"}:
        ready.artifact.path.chmod(stat.S_IWRITE | stat.S_IREAD)
    if damage == "missing":
        ready.artifact.path.unlink()
    elif damage == "corrupt":
        ready.artifact.path.write_bytes(b"bad bytes")
    else:
        snapshots.requests = ()
    with pytest.raises((LocalArtifactVerificationError, SnapshotArtifactInvalid)):
        _resolve(resolver, ready)
    assert not requests.calls
    assert not snapshots.expired
    assert len(snapshots.commands) == 1
