from __future__ import annotations

from collections import deque
from datetime import UTC, date, datetime
import hashlib
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from backend.resources.sleeper_data import (
    ApiRequestCandidate,
    ArtifactFailure,
    BeginSnapshotBuild,
    ClaimedSnapshotBuild,
    DataSnapshot,
    ExistingBuildingSnapshot,
    ExistingReadySnapshot,
    InlineVerifiedPayload,
    ObjectVerifiedPayload,
    SealSnapshot,
    SnapshotBuildState,
    SnapshotCandidateQuery,
    SnapshotFailure,
    SnapshotPlanningContext,
    SeasonRosterIdentity,
)
from backend.services.datalayer import (
    DatalayerSnapshotService,
    EndpointKind,
    InternalDatalayerFailure,
    LocalArtifactKind,
    LocalDatalayerFileStore,
    MaterializedSnapshot,
    SnapshotRequest,
    SnapshotStatus,
    SnapshotUnavailable,
)
from backend.services.datalayer.canonical_json import (
    JsonValue,
    canonical_json_bytes,
    parse_json_bytes,
)
from backend.services.datalayer.local_files import StoredLocalArtifact
from backend.services.datalayer.snapshot_service import SnapshotMaterializationInput


SEASON_ID = UUID("11111111-1111-1111-1111-111111111111")
COMPETITION_ID = UUID("22222222-2222-2222-2222-222222222222")
FIXTURES = Path(__file__).parents[4] / "datalayer" / "tests" / "fixtures" / "sleeper"
PAYLOAD_FILES = {
    EndpointKind.LEAGUE: "league.json",
    EndpointKind.LEAGUE_USERS: "users.json",
    EndpointKind.NFL_STATE: "state.json",
    EndpointKind.PLAYER_CATALOG: "players.json",
    EndpointKind.LEAGUE_ROSTERS: "rosters.json",
    EndpointKind.MATCHUPS: "matchups_week1.json",
    EndpointKind.TRANSACTIONS: "transactions_week1.json",
}


class FakePlanning:
    def get_snapshot_planning_context(self, competition_season_id: UUID):
        assert competition_season_id == SEASON_ID
        return SnapshotPlanningContext(
            competition_id=COMPETITION_ID,
            competition_season_id=SEASON_ID,
            sleeper_league_id="123",
            season_year=2026,
            playoff_start_week=14,
            playoff_team_count=4,
            draft_rounds=0,
            league_average_match=0,
        )


class FakeRosterIdentities:
    def __init__(
        self,
        *,
        roster_ids: tuple[int, ...] = (1, 2),
        competition_id: UUID = COMPETITION_ID,
    ) -> None:
        self.calls: list[UUID] = []
        self.identities = tuple(
            SeasonRosterIdentity(
                competition_id=competition_id,
                competition_season_id=SEASON_ID,
                season_roster_id=UUID(int=100 + roster_id),
                franchise_id=UUID(int=200 + roster_id),
                sleeper_roster_id=str(roster_id),
            )
            for roster_id in roster_ids
        )

    def list_roster_identities(
        self,
        competition_season_id: UUID,
    ) -> tuple[SeasonRosterIdentity, ...]:
        self.calls.append(competition_season_id)
        return self.identities


class FakeRequests:
    def __init__(
        self,
        *,
        files: LocalDatalayerFileStore,
        missing_last: bool = False,
        object_kind: EndpointKind | None = None,
    ) -> None:
        self.files = files
        self.missing_last = missing_last
        self.object_kind = object_kind
        self.payloads: dict[UUID, tuple[ApiRequestCandidate, JsonValue]] = {}

    def list_snapshot_candidates(self, query: SnapshotCandidateQuery):
        from backend.services.datalayer.snapshot_selection import (
            plan_snapshot_requirements,
        )

        request = SnapshotRequest(
            competition_season_id=query.competition_season_id,
            through_week=query.through_week,
            as_of_date=date(2026, 10, 27),
        )
        context = FakePlanning().get_snapshot_planning_context(SEASON_ID)
        requirements = plan_snapshot_requirements(request, context)
        self.payloads.clear()
        for index, requirement in enumerate(requirements.entries, start=1):
            endpoint = requirement.request
            fixture = FIXTURES / PAYLOAD_FILES[endpoint.endpoint_kind]
            payload = parse_json_bytes(fixture.read_bytes())
            content = canonical_json_bytes(payload)
            candidate = ApiRequestCandidate(
                request_id=UUID(int=index),
                competition_season_id=(
                    None
                    if endpoint.endpoint_kind
                    in {EndpointKind.NFL_STATE, EndpointKind.PLAYER_CATALOG}
                    else SEASON_ID
                ),
                endpoint_kind=endpoint.endpoint_kind,
                scope_key=endpoint.scope_key,
                week=endpoint.week,
                bracket_kind=endpoint.bracket_kind,
                requested_at=datetime(2026, 11, 1, index, tzinfo=UTC),
                completed_at=datetime(2026, 11, 1, index, 1, tzinfo=UTC),
                payload_id=UUID(int=1_000 + index),
                response_sha256=hashlib.sha256(content).hexdigest(),
            )
            self.payloads[candidate.request_id] = (candidate, payload)
        candidates = tuple(candidate for candidate, _ in self.payloads.values())
        return candidates[:-1] if self.missing_last else candidates

    def resolve_verified_payloads(self, request_ids):
        resolved = []
        for request_id in request_ids:
            candidate, payload = self.payloads[request_id]
            content = canonical_json_bytes(payload)
            common = {
                "request_id": request_id,
                "scope_key": candidate.scope_key,
                "sha256": candidate.response_sha256,
                "byte_length": len(content),
                "media_type": "application/json",
            }
            if candidate.endpoint_kind is self.object_kind:
                receipt = self.files.store_bytes(LocalArtifactKind.PAYLOAD, content)
                resolved.append(
                    ObjectVerifiedPayload(storage_key=receipt.storage_key, **common)
                )
            else:
                resolved.append(InlineVerifiedPayload(payload=payload, **common))
        return tuple(resolved)


class FakeSnapshots:
    def __init__(
        self,
        states: tuple[SnapshotBuildState, ...] = (),
        observed: tuple[DataSnapshot, ...] = (),
    ) -> None:
        self.states = deque(states)
        self.observed = deque(observed)
        self.current: DataSnapshot | None = None
        self.sealed: SealSnapshot | None = None
        self.failed: list[SnapshotFailure] = []
        self.expired: list[ArtifactFailure] = []
        self.stale = False

    def begin_or_get(self, command: BeginSnapshotBuild):
        if self.states:
            state = self.states.popleft()
            self.current = state.snapshot
            return state
        self.current = _snapshot_from_command(command)
        return ClaimedSnapshotBuild(snapshot=self.current)

    def seal_ready(self, snapshot_id: UUID, command: SealSnapshot):
        assert self.current is not None and snapshot_id == self.current.id
        self.sealed = command
        self.current = self.current.model_copy(
            update={
                "status": SnapshotStatus.READY,
                "artifact": command.artifact,
                "completeness_warnings": command.completeness_warnings,
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
        return self.stale

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


class FakeMaterializer:
    def __init__(self, output: Path) -> None:
        self.output = output.resolve()
        self.calls: list[SnapshotMaterializationInput] = []
        self.failure: Exception | None = None

    def materialize(self, materialization: SnapshotMaterializationInput):
        self.calls.append(materialization)
        if self.failure is not None:
            raise self.failure
        content = b"synthetic snapshot sqlite"
        self.output.write_bytes(content)
        return MaterializedSnapshot(
            path=self.output,
            sha256=hashlib.sha256(content).hexdigest(),
            byte_length=len(content),
        )


def _request() -> SnapshotRequest:
    return SnapshotRequest(
        competition_season_id=SEASON_ID,
        through_week=1,
        as_of_date=date(2026, 10, 27),
    )


def _snapshot_from_command(
    command: BeginSnapshotBuild,
    *,
    status: SnapshotStatus = SnapshotStatus.BUILDING,
    artifact=None,
) -> DataSnapshot:
    return DataSnapshot(
        id=uuid4(),
        competition_id=COMPETITION_ID,
        primary_competition_season_id=command.competition_season_id,
        build_key=command.build_key,
        through_week=command.through_week,
        as_of_date=command.as_of_date,
        status=status,
        snapshot_projection_version=command.snapshot_projection_version,
        code_version=command.code_version,
        completeness_warnings=(),
        failure=None,
        artifact=artifact,
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC) if status is SnapshotStatus.READY else None,
    )


def _service(
    tmp_path: Path,
    *,
    snapshots: FakeSnapshots | None = None,
    requests: FakeRequests | None = None,
    roster_identities: FakeRosterIdentities | None = None,
    monotonic_clock=lambda: 0.0,
    delay=lambda _: None,
) -> tuple[
    DatalayerSnapshotService,
    FakeSnapshots,
    FakeMaterializer,
    LocalDatalayerFileStore,
]:
    files = LocalDatalayerFileStore(tmp_path / "data")
    lifecycle = snapshots or FakeSnapshots()
    reader = requests or FakeRequests(files=files)
    materializer = FakeMaterializer(tmp_path / "synthetic.sqlite")
    return (
        DatalayerSnapshotService(
            planning=FakePlanning(),
            roster_identities=roster_identities or FakeRosterIdentities(),
            requests=reader,
            snapshots=lifecycle,
            materializer=materializer,
            files=files,
            code_version="test",
            wait_timeout_seconds=1,
            stale_after_seconds=300,
            poll_interval_seconds=0.1,
            monotonic_clock=monotonic_clock,
            delay=delay,
        ),
        lifecycle,
        materializer,
        files,
    )


def test_claimed_build_replays_inline_and_object_payloads_then_seals(
    tmp_path: Path,
) -> None:
    files = LocalDatalayerFileStore(tmp_path / "data")
    requests = FakeRequests(files=files, object_kind=EndpointKind.PLAYER_CATALOG)
    service, snapshots, materializer, _ = _service(tmp_path, requests=requests)

    ready = service.get_or_create(_request())

    assert ready.artifact.path.exists()
    assert snapshots.sealed is not None
    assert len(snapshots.sealed.requests) == 7
    assert len(materializer.calls) == 1
    endpoint_kinds = [
        entry.records.endpoint_kind
        for entry in materializer.calls[0].endpoint_records
    ]
    assert endpoint_kinds == [
        EndpointKind.LEAGUE,
        EndpointKind.LEAGUE_USERS,
        EndpointKind.NFL_STATE,
        EndpointKind.PLAYER_CATALOG,
        EndpointKind.LEAGUE_ROSTERS,
        EndpointKind.MATCHUPS,
        EndpointKind.TRANSACTIONS,
    ]


@pytest.mark.parametrize(
    "roster_identities",
    [
        FakeRosterIdentities(roster_ids=(1,)),
        FakeRosterIdentities(
            competition_id=UUID("33333333-3333-3333-3333-333333333333")
        ),
    ],
)
def test_invalid_roster_identity_input_fails_the_claim(
    tmp_path: Path,
    roster_identities: FakeRosterIdentities,
) -> None:
    service, snapshots, materializer, _ = _service(
        tmp_path,
        roster_identities=roster_identities,
    )

    with pytest.raises(InternalDatalayerFailure):
        service.get_or_create(_request())

    assert snapshots.failed[0].code == "snapshot_build_failed"
    assert snapshots.sealed is None
    assert materializer.calls == []


def test_healthy_ready_snapshot_is_verified_without_rebuilding(tmp_path: Path) -> None:
    files = LocalDatalayerFileStore(tmp_path / "data")
    receipt = files.store_bytes(LocalArtifactKind.SNAPSHOT, b"ready")
    command = BeginSnapshotBuild(
        competition_season_id=SEASON_ID,
        through_week=1,
        as_of_date=date(2026, 10, 27),
        build_key="a" * 64,
        snapshot_projection_version="2",
        code_version="test",
    )
    stored = _snapshot_from_command(
        command,
        status=SnapshotStatus.READY,
        artifact=receipt,
    )
    snapshots = FakeSnapshots((ExistingReadySnapshot(snapshot=stored),))
    service, _, materializer, _ = _service(tmp_path, snapshots=snapshots)

    ready = service.get_or_create(_request())

    assert ready.id == stored.id
    assert materializer.calls == []


def test_corrupt_ready_snapshot_is_expired_before_replacement(tmp_path: Path) -> None:
    files = LocalDatalayerFileStore(tmp_path / "data")
    missing_sha = "b" * 64
    missing = StoredLocalArtifact(
        storage_key=f"snapshots/sha256/bb/{missing_sha}.sqlite",
        sha256=missing_sha,
        byte_length=10,
    )
    command = BeginSnapshotBuild(
        competition_season_id=SEASON_ID,
        through_week=1,
        as_of_date=date(2026, 10, 27),
        build_key="a" * 64,
        snapshot_projection_version="2",
        code_version="test",
    )
    stored = _snapshot_from_command(
        command,
        status=SnapshotStatus.READY,
        artifact=missing,
    )
    snapshots = FakeSnapshots((ExistingReadySnapshot(snapshot=stored),))
    service, lifecycle, materializer, _ = _service(tmp_path, snapshots=snapshots)

    ready = service.get_or_create(_request())

    assert lifecycle.expired[0].code == "snapshot_artifact_unusable"
    assert ready.id != stored.id
    assert len(materializer.calls) == 1


def test_missing_required_scope_marks_claim_failed(tmp_path: Path) -> None:
    files = LocalDatalayerFileStore(tmp_path / "data")
    reader = FakeRequests(files=files, missing_last=True)
    service, snapshots, materializer, _ = _service(tmp_path, requests=reader)

    with pytest.raises(SnapshotUnavailable) as captured:
        service.get_or_create(_request())

    assert captured.value.missing_scopes
    assert snapshots.failed[0].code == "snapshot_inputs_unavailable"
    assert snapshots.sealed is None
    assert materializer.calls == []


def test_materializer_failure_marks_claim_failed_without_membership(
    tmp_path: Path,
) -> None:
    service, snapshots, materializer, _ = _service(tmp_path)
    materializer.failure = RuntimeError("private implementation detail")

    with pytest.raises(InternalDatalayerFailure):
        service.get_or_create(_request())

    assert snapshots.failed[0].code == "snapshot_build_failed"
    assert snapshots.failed[0].summary == "Snapshot build failed unexpectedly"
    assert snapshots.sealed is None


def test_existing_build_times_out_without_stealing_a_healthy_claim(
    tmp_path: Path,
) -> None:
    command = BeginSnapshotBuild(
        competition_season_id=SEASON_ID,
        through_week=1,
        as_of_date=date(2026, 10, 27),
        build_key="a" * 64,
        snapshot_projection_version="2",
        code_version="test",
    )
    building = _snapshot_from_command(command)
    snapshots = FakeSnapshots((ExistingBuildingSnapshot(snapshot=building),))
    ticks = iter((0.0, 0.0, 1.0))
    service, _, _, _ = _service(
        tmp_path,
        snapshots=snapshots,
        monotonic_clock=lambda: next(ticks),
    )

    with pytest.raises(SnapshotUnavailable, match="wait budget"):
        service.get_or_create(_request())


def test_existing_build_waits_for_and_reuses_ready_result(tmp_path: Path) -> None:
    files = LocalDatalayerFileStore(tmp_path / "data")
    receipt = files.store_bytes(LocalArtifactKind.SNAPSHOT, b"ready")
    command = BeginSnapshotBuild(
        competition_season_id=SEASON_ID,
        through_week=1,
        as_of_date=date(2026, 10, 27),
        build_key="a" * 64,
        snapshot_projection_version="2",
        code_version="test",
    )
    building = _snapshot_from_command(command)
    ready_state = building.model_copy(
        update={
            "status": SnapshotStatus.READY,
            "artifact": receipt,
            "completed_at": datetime.now(UTC),
        }
    )
    snapshots = FakeSnapshots(
        (ExistingBuildingSnapshot(snapshot=building),),
        observed=(ready_state,),
    )
    service, _, materializer, _ = _service(tmp_path, snapshots=snapshots)

    ready = service.get_or_create(_request())

    assert ready.id == building.id
    assert materializer.calls == []


def test_stale_existing_build_is_failed_before_reclaim(tmp_path: Path) -> None:
    command = BeginSnapshotBuild(
        competition_season_id=SEASON_ID,
        through_week=1,
        as_of_date=date(2026, 10, 27),
        build_key="a" * 64,
        snapshot_projection_version="2",
        code_version="test",
    )
    building = _snapshot_from_command(command)
    snapshots = FakeSnapshots((ExistingBuildingSnapshot(snapshot=building),))
    snapshots.stale = True
    service, lifecycle, materializer, _ = _service(
        tmp_path,
        snapshots=snapshots,
    )

    ready = service.get_or_create(_request())

    assert ready.id != building.id
    assert lifecycle.sealed is not None
    assert len(materializer.calls) == 1
