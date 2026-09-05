from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest

from backend.resources.sleeper_data.snapshots import (
    ArtifactFailure,
    BeginSnapshotBuild,
    ClaimedSnapshotBuild,
    DataSnapshot,
    ExistingBuildingSnapshot,
    ExistingReadySnapshot,
    SealSnapshot,
    SnapshotBuildState,
    SnapshotFailure,
    SnapshotRequestMembership,
    SnapshotSeasonMembership,
)
from backend.services.datalayer.contracts import SnapshotStatus
from backend.services.datalayer.canonical_json import parse_json_bytes
from backend.services.datalayer.errors import (
    DatalayerScopeConflict,
    InternalDatalayerFailure,
    SnapshotUnavailable,
)
from backend.services.datalayer.local_files import LocalDatalayerFileStore
from backend.services.datalayer.resolved_snapshot_builder import (
    DatalayerResolvedSnapshotBuilder,
    canonical_resolved_snapshot_build_key,
)
from backend.services.datalayer.snapshot_inputs import ResolvedSnapshotInputs
from backend.services.datalayer.snapshot_sqlite import SQLiteSnapshotMaterializer
from backend.services.datalayer.sleeper.scope import EndpointKind
from backend.tests.services.datalayer.test_snapshot_inputs import (
    _Candidates,
    _resolve,
)


FIXTURES = Path(__file__).parents[4] / "datalayer" / "tests" / "fixtures" / "sleeper"


class _BuilderCandidates(_Candidates):
    def _payload(self, kind, season_id):
        if kind is EndpointKind.PLAYER_CATALOG:
            return parse_json_bytes((FIXTURES / "players.json").read_bytes())
        return super()._payload(kind, season_id)


def _inputs(
    *,
    id_salt: str = "base",
) -> tuple[ResolvedSnapshotInputs, _BuilderCandidates]:
    candidates = _BuilderCandidates(id_salt=id_salt)
    state, _ = _resolve(candidates)
    assert isinstance(state, ResolvedSnapshotInputs)
    return state, candidates


class _Requests:
    def __init__(self, candidates: _Candidates) -> None:
        self._candidates = candidates
        self.calls: list[tuple[UUID, ...]] = []
        self.mismatch = False

    def resolve_verified_payloads(self, request_ids):
        self.calls.append(tuple(request_ids))
        payloads = self._candidates.resolve_verified_payloads(request_ids)
        if self.mismatch:
            payloads = (
                payloads[0].model_copy(update={"sha256": "f" * 64}),
                *payloads[1:],
            )
        return payloads


class _Snapshots:
    def __init__(
        self,
        inputs: ResolvedSnapshotInputs,
        *,
        states: tuple[SnapshotBuildState, ...] = (),
        observed: tuple[DataSnapshot, ...] = (),
    ) -> None:
        self.inputs = inputs
        self.states = deque(states)
        self.observed = deque(observed)
        self.current: DataSnapshot | None = None
        self.requests: tuple[SnapshotRequestMembership, ...] = ()
        self.sealed: SealSnapshot | None = None
        self.failed: list[SnapshotFailure] = []
        self.expired: list[ArtifactFailure] = []
        self.commands: list[BeginSnapshotBuild] = []
        self.stale = False

    def begin_or_get(self, command: BeginSnapshotBuild):
        self.commands.append(command)
        if self.states:
            state = self.states.popleft()
            self.current = state.snapshot
            return state
        if (
            self.current is not None
            and self.current.status is SnapshotStatus.READY
            and self.current.build_key == command.build_key
        ):
            return ExistingReadySnapshot(snapshot=self.current)
        self.current = _snapshot_from_command(self.inputs, command)
        return ClaimedSnapshotBuild(snapshot=self.current)

    def seal_ready(self, snapshot_id: UUID, command: SealSnapshot):
        assert self.current is not None and snapshot_id == self.current.id
        self.sealed = command
        self.requests = command.requests
        by_id = {
            season.identity.competition_season_id: season
            for season in self.inputs.seasons
        }
        included = tuple(
            SnapshotSeasonMembership(
                competition_id=(
                    by_id[item.competition_season_id].identity.competition_id
                ),
                competition_season_id=item.competition_season_id,
                sleeper_league_id=(
                    by_id[item.competition_season_id].identity.sleeper_league_id
                ),
                season_year=by_id[item.competition_season_id].identity.season_year,
                sequence_number=(
                    by_id[item.competition_season_id].identity.sequence_number
                ),
                role=item.role,
                through_week=item.through_week,
            )
            for item in command.seasons
        )
        self.current = self.current.model_copy(
            update={
                "status": SnapshotStatus.READY,
                "artifact": command.artifact,
                "completeness_warnings": command.completeness_warnings,
                "included_seasons": included,
                "completed_at": datetime.now(UTC),
            }
        )
        return self.current

    def mark_failed(self, snapshot_id: UUID, failure: SnapshotFailure):
        assert self.current is not None and snapshot_id == self.current.id
        self.failed.append(failure)
        self.current = self.current.model_copy(
            update={"status": SnapshotStatus.FAILED, "failure": failure}
        )
        return self.current

    def fail_stale_build(self, build_key: str, stale_before: datetime):
        del build_key, stale_before
        if not self.stale:
            return False
        self.stale = False
        assert self.current is not None
        self.current = self.current.model_copy(update={"status": SnapshotStatus.FAILED})
        return True

    def expire_unusable(self, snapshot_id: UUID, failure: ArtifactFailure):
        assert self.current is not None and snapshot_id == self.current.id
        self.expired.append(failure)
        self.current = self.current.model_copy(
            update={"status": SnapshotStatus.EXPIRED}
        )
        return self.current

    def get(self, snapshot_id: UUID):
        assert self.current is not None and snapshot_id == self.current.id
        if self.observed:
            self.current = self.observed.popleft()
        return self.current

    def list_requests(self, snapshot_id: UUID):
        assert self.current is not None and snapshot_id == self.current.id
        return self.requests


def _snapshot_from_command(
    inputs: ResolvedSnapshotInputs,
    command: BeginSnapshotBuild,
    *,
    status: SnapshotStatus = SnapshotStatus.BUILDING,
) -> DataSnapshot:
    return DataSnapshot(
        id=uuid4(),
        competition_id=inputs.seasons[0].identity.competition_id,
        primary_competition_season_id=command.competition_season_id,
        build_key=command.build_key,
        input_revision=command.input_revision,
        through_week=command.through_week,
        as_of_date=command.as_of_date,
        status=status,
        snapshot_projection_version=command.snapshot_projection_version,
        code_version=command.code_version,
        completeness_warnings=(),
        failure=None,
        artifact=None,
        included_seasons=(),
        created_at=datetime.now(UTC),
        completed_at=None,
    )


def _builder(
    tmp_path: Path,
    inputs: ResolvedSnapshotInputs,
    candidates: _Candidates,
    *,
    snapshots: _Snapshots | None = None,
    materializer=None,
    monotonic_clock=lambda: 0.0,
):
    files = LocalDatalayerFileStore(tmp_path / "data")
    lifecycle = snapshots or _Snapshots(inputs)
    requests = _Requests(candidates)
    builder = DatalayerResolvedSnapshotBuilder(
        requests=requests,
        snapshots=lifecycle,
        materializer=materializer
        or SQLiteSnapshotMaterializer(tmp_path / "staging"),
        files=files,
        code_version="test",
        wait_timeout_seconds=1,
        stale_after_seconds=300,
        poll_interval_seconds=0.1,
        monotonic_clock=monotonic_clock,
        delay=lambda _: None,
    )
    return builder, lifecycle, requests


def test_claimed_build_replays_only_frozen_requests_and_seals_every_season(
    tmp_path: Path,
) -> None:
    inputs, candidates = _inputs()
    builder, snapshots, requests = _builder(tmp_path, inputs, candidates)

    ready = builder.get_or_create(inputs)

    assert requests.calls == [
        tuple(entry.request_id for entry in inputs.manifest.entries)
    ]
    assert snapshots.commands[0].input_revision == inputs.input_revision
    assert snapshots.sealed is not None
    assert [item.competition_season_id for item in snapshots.sealed.seasons] == [
        season.identity.competition_season_id for season in inputs.seasons
    ]
    assert ready.input_revision == inputs.input_revision
    assert [season.through_week for season in ready.included_seasons] == [18, 3]
    assert ready.artifact.path.exists()


def test_identical_facts_with_new_request_ids_reuse_original_audit_membership(
    tmp_path: Path,
) -> None:
    inputs, candidates = _inputs(id_salt="first")
    builder, snapshots, _ = _builder(tmp_path, inputs, candidates)
    first = builder.get_or_create(inputs)
    original_requests = snapshots.requests

    changed_entries = tuple(
        entry.model_copy(
            update={
                "request_id": uuid5(
                    NAMESPACE_URL,
                    f"replacement:{entry.scope_key.value}",
                )
            }
        )
        for entry in inputs.manifest.entries
    )
    replacement_manifest = inputs.manifest.model_copy(
        update={"entries": changed_entries}
    )
    replacement = inputs.model_copy(update={"manifest": replacement_manifest})
    unused_candidates = _Candidates(id_salt="replacement")
    replacement_requests = _Requests(unused_candidates)
    reuse = DatalayerResolvedSnapshotBuilder(
        requests=replacement_requests,
        snapshots=snapshots,
        materializer=SQLiteSnapshotMaterializer(tmp_path / "unused-staging"),
        files=LocalDatalayerFileStore(tmp_path / "data"),
        code_version="test",
    )

    second = reuse.get_or_create(replacement)

    assert second.id == first.id
    assert replacement_requests.calls == []
    assert snapshots.requests == original_requests


def test_build_key_uses_factual_revision_not_request_receipts() -> None:
    inputs, _ = _inputs(id_salt="first")
    audit_changed, _ = _inputs(id_salt="second")

    assert canonical_resolved_snapshot_build_key(inputs) == (
        canonical_resolved_snapshot_build_key(audit_changed)
    )
    changed = inputs.model_copy(update={"input_revision": "e" * 64})
    assert canonical_resolved_snapshot_build_key(inputs) != (
        canonical_resolved_snapshot_build_key(changed)
    )


def test_joiner_waits_for_and_verifies_the_sealed_result(tmp_path: Path) -> None:
    inputs, candidates = _inputs()
    winner, completed, _ = _builder(tmp_path, inputs, candidates)
    ready = winner.get_or_create(inputs)
    stored_ready = completed.current
    assert stored_ready is not None
    building = stored_ready.model_copy(
        update={
            "status": SnapshotStatus.BUILDING,
            "artifact": None,
            "included_seasons": (),
            "completed_at": None,
        }
    )
    completed.states.append(ExistingBuildingSnapshot(snapshot=building))
    completed.observed.append(stored_ready)
    joiner_requests = _Requests(candidates)
    joiner = DatalayerResolvedSnapshotBuilder(
        requests=joiner_requests,
        snapshots=completed,
        materializer=SQLiteSnapshotMaterializer(tmp_path / "unused-staging"),
        files=LocalDatalayerFileStore(tmp_path / "data"),
        code_version="test",
    )

    joined = joiner.get_or_create(inputs)

    assert joined.id == ready.id
    assert joiner_requests.calls == []


def test_sealed_request_disagreement_expires_before_rebuild(tmp_path: Path) -> None:
    inputs, candidates = _inputs()
    builder, snapshots, _ = _builder(tmp_path, inputs, candidates)
    first = builder.get_or_create(inputs)
    snapshots.requests = (
        snapshots.requests[0].model_copy(update={"response_sha256": "f" * 64}),
        *snapshots.requests[1:],
    )

    replacement = builder.get_or_create(inputs)

    assert snapshots.expired[0].code == "snapshot_artifact_unusable"
    assert replacement.id != first.id


def test_payload_receipt_mismatch_fails_claim_without_sealing(tmp_path: Path) -> None:
    inputs, candidates = _inputs()
    builder, snapshots, requests = _builder(tmp_path, inputs, candidates)
    requests.mismatch = True

    with pytest.raises(DatalayerScopeConflict, match="frozen manifest"):
        builder.get_or_create(inputs)

    assert snapshots.sealed is None
    assert snapshots.failed[0].code == "snapshot_build_rejected"


def test_unexpected_materializer_failure_is_sanitized(tmp_path: Path) -> None:
    class _BrokenMaterializer:
        def materialize(self, materialization):
            del materialization
            raise RuntimeError("private detail")

    inputs, candidates = _inputs()
    builder, snapshots, _ = _builder(
        tmp_path,
        inputs,
        candidates,
        materializer=_BrokenMaterializer(),
    )

    with pytest.raises(InternalDatalayerFailure):
        builder.get_or_create(inputs)

    assert snapshots.failed[0].code == "snapshot_build_failed"
    assert snapshots.failed[0].summary == "Snapshot build failed unexpectedly"


def test_existing_build_timeout_and_one_stale_recovery(tmp_path: Path) -> None:
    inputs, candidates = _inputs()
    command = BeginSnapshotBuild(
        competition_season_id=inputs.primary.competition_season_id,
        through_week=inputs.primary.through_week,
        as_of_date=inputs.primary.as_of_date,
        build_key=canonical_resolved_snapshot_build_key(inputs),
        snapshot_projection_version="3",
        code_version="test",
        input_revision=inputs.input_revision,
    )
    building = _snapshot_from_command(inputs, command)
    timeout_lifecycle = _Snapshots(
        inputs,
        states=(ExistingBuildingSnapshot(snapshot=building),),
    )
    ticks = iter((0.0, 0.0, 1.0))
    timeout_builder, _, _ = _builder(
        tmp_path / "timeout",
        inputs,
        candidates,
        snapshots=timeout_lifecycle,
        monotonic_clock=lambda: next(ticks),
    )
    with pytest.raises(SnapshotUnavailable, match="wait budget"):
        timeout_builder.get_or_create(inputs)

    stale_lifecycle = _Snapshots(
        inputs,
        states=(ExistingBuildingSnapshot(snapshot=building),),
    )
    stale_lifecycle.stale = True
    stale_builder, _, _ = _builder(
        tmp_path / "stale",
        inputs,
        candidates,
        snapshots=stale_lifecycle,
    )
    ready = stale_builder.get_or_create(inputs)

    assert ready.input_revision == inputs.input_revision
    assert len(stale_lifecycle.commands) == 2
