"""Build one immutable v3 snapshot from already-resolved factual inputs."""

from __future__ import annotations

from collections.abc import Callable, Collection
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
from time import monotonic, sleep
from typing import Protocol, assert_never
from uuid import UUID

from backend.resources.sleeper_data.requests import (
    InlineVerifiedPayload,
    ObjectVerifiedPayload,
    VerifiedPayload,
)
from backend.resources.sleeper_data.snapshots import (
    ArtifactFailure,
    BeginSnapshotBuild,
    ClaimedSnapshotBuild,
    DataSnapshot,
    ExistingBuildingSnapshot,
    ExistingReadySnapshot,
    SealSnapshot,
    SealSnapshotSeason,
    SnapshotBuildState,
    SnapshotFailure,
    SnapshotRequestMembership,
)
from backend.services.datalayer.canonical_json import (
    JsonValue,
    canonical_json_sha256,
    parse_json_bytes,
)
from backend.services.datalayer.contracts import (
    ReadyDataSnapshot,
    ReadySnapshotSeason,
    SnapshotStatus,
)
from backend.services.datalayer.errors import (
    DatalayerError,
    DatalayerScopeConflict,
    InternalDatalayerFailure,
    SnapshotUnavailable,
)
from backend.services.datalayer.local_files import (
    LocalArtifactKind,
    LocalArtifactVerificationError,
    StoredLocalArtifact,
    VerifiedLocalArtifact,
)
from backend.services.datalayer.snapshot_inputs import ResolvedSnapshotInputs
from backend.services.datalayer.snapshot_replay import normalize_snapshot_payload
from backend.services.datalayer.snapshot_service import (
    MaterializedSnapshot,
    SnapshotEndpointRecords,
)
from backend.services.datalayer.snapshot_sqlite import (
    ResolvedSnapshotMaterializationInput,
    SnapshotArtifactInvalid,
    verify_sealed_snapshot_file,
)
from backend.services.datalayer.versions import (
    RESOLVED_SNAPSHOT_PROJECTION_VERSION,
    SNAPSHOT_DERIVATION_VERSION,
)


WallClock = Callable[[], datetime]
MonotonicClock = Callable[[], float]


class ResolvedSnapshotRequestReader(Protocol):
    def resolve_verified_payloads(
        self,
        request_ids: Collection[UUID],
    ) -> tuple[VerifiedPayload, ...]: ...


class ResolvedSnapshotLifecycle(Protocol):
    def begin_or_get(self, command: BeginSnapshotBuild) -> SnapshotBuildState: ...

    def seal_ready(self, snapshot_id: UUID, command: SealSnapshot) -> DataSnapshot: ...

    def mark_failed(
        self,
        snapshot_id: UUID,
        failure: SnapshotFailure,
    ) -> DataSnapshot: ...

    def fail_stale_build(self, build_key: str, stale_before: datetime) -> bool: ...

    def expire_unusable(
        self,
        snapshot_id: UUID,
        failure: ArtifactFailure,
    ) -> DataSnapshot: ...

    def get(self, snapshot_id: UUID) -> DataSnapshot: ...

    def list_requests(
        self,
        snapshot_id: UUID,
    ) -> tuple[SnapshotRequestMembership, ...]: ...


class ResolvedSnapshotMaterializer(Protocol):
    def materialize(
        self,
        materialization: ResolvedSnapshotMaterializationInput,
    ) -> MaterializedSnapshot: ...


class ResolvedSnapshotFileStore(Protocol):
    def store_file(
        self,
        kind: LocalArtifactKind,
        source: Path,
    ) -> StoredLocalArtifact: ...

    def open_verified(
        self,
        storage_key: str,
        *,
        expected_sha256: str,
        expected_byte_length: int,
    ) -> VerifiedLocalArtifact: ...


def canonical_resolved_snapshot_build_key(
    inputs: ResolvedSnapshotInputs,
    snapshot_projection_version: str = RESOLVED_SNAPSHOT_PROJECTION_VERSION,
) -> str:
    """Return the build identity for one complete frozen factual revision."""

    version = _nonblank(snapshot_projection_version, "snapshot_projection_version")
    primary = inputs.primary
    return canonical_json_sha256(
        {
            "as_of_date": primary.as_of_date.isoformat(),
            "competition_season_id": str(primary.competition_season_id),
            "input_revision": inputs.input_revision,
            "snapshot_projection_version": version,
            "snapshot_derivation_version": SNAPSHOT_DERIVATION_VERSION,
            "through_week": primary.through_week,
        }
    )


class DatalayerResolvedSnapshotBuilder:
    """Claim, replay, materialize, persist, and seal frozen resolved inputs."""

    def __init__(
        self,
        *,
        requests: ResolvedSnapshotRequestReader,
        snapshots: ResolvedSnapshotLifecycle,
        materializer: ResolvedSnapshotMaterializer,
        files: ResolvedSnapshotFileStore,
        code_version: str,
        snapshot_projection_version: str = RESOLVED_SNAPSHOT_PROJECTION_VERSION,
        wait_timeout_seconds: float = 30.0,
        stale_after_seconds: float = 300.0,
        poll_interval_seconds: float = 0.1,
        clock: WallClock | None = None,
        monotonic_clock: MonotonicClock = monotonic,
        delay: Callable[[float], None] = sleep,
    ) -> None:
        self._code_version = _nonblank(code_version, "code_version")
        self._projection_version = _nonblank(
            snapshot_projection_version,
            "snapshot_projection_version",
        )
        if self._projection_version != RESOLVED_SNAPSHOT_PROJECTION_VERSION:
            raise ValueError("resolved snapshot builder requires projection version 3")
        self._wait_timeout = _positive_number(
            wait_timeout_seconds,
            "wait_timeout_seconds",
        )
        self._stale_after = _positive_number(
            stale_after_seconds,
            "stale_after_seconds",
        )
        self._poll_interval = _positive_number(
            poll_interval_seconds,
            "poll_interval_seconds",
        )
        self._requests = requests
        self._snapshots = snapshots
        self._materializer = materializer
        self._files = files
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic_clock
        self._delay = delay

    def get_or_create(self, inputs: ResolvedSnapshotInputs) -> ReadyDataSnapshot:
        build_key = canonical_resolved_snapshot_build_key(
            inputs,
            self._projection_version,
        )
        command = BeginSnapshotBuild(
            competition_season_id=inputs.primary.competition_season_id,
            through_week=inputs.primary.through_week,
            as_of_date=inputs.primary.as_of_date,
            build_key=build_key,
            snapshot_projection_version=self._projection_version,
            code_version=self._code_version,
            input_revision=inputs.input_revision,
        )
        while True:
            state = self._snapshots.begin_or_get(command)
            if isinstance(state, ClaimedSnapshotBuild):
                ready = self._build_claimed(inputs, state.snapshot)
            elif isinstance(state, ExistingReadySnapshot):
                ready = self._reuse_ready(inputs, state.snapshot)
            elif isinstance(state, ExistingBuildingSnapshot):
                ready = self._wait_for_existing(inputs, state.snapshot)
            else:
                assert_never(state)
            if ready is not None:
                return ready

    def _build_claimed(
        self,
        inputs: ResolvedSnapshotInputs,
        claimed: DataSnapshot,
    ) -> ReadyDataSnapshot | None:
        materialized: MaterializedSnapshot | None = None
        try:
            payloads = self._requests.resolve_verified_payloads(
                [entry.request_id for entry in inputs.manifest.entries]
            )
            endpoint_records = self._replay(inputs, payloads)
            materialized = self._materializer.materialize(
                ResolvedSnapshotMaterializationInput(
                    inputs=inputs,
                    build_key=claimed.build_key,
                    snapshot_projection_version=self._projection_version,
                    endpoint_records=endpoint_records,
                )
            )
            receipt = self._files.store_file(
                LocalArtifactKind.SNAPSHOT,
                materialized.path,
            )
            if (
                receipt.sha256 != materialized.sha256
                or receipt.byte_length != materialized.byte_length
            ):
                raise DatalayerScopeConflict(
                    "stored snapshot artifact differs from materializer output"
                )
            sealed = self._snapshots.seal_ready(
                claimed.id,
                SealSnapshot(
                    requests=tuple(
                        SnapshotRequestMembership(
                            request_id=entry.request_id,
                            endpoint_kind=entry.endpoint_kind,
                            scope_key=entry.scope_key,
                            response_sha256=entry.response_sha256,
                            selection_role=entry.selection_role,
                        )
                        for entry in inputs.manifest.entries
                    ),
                    seasons=tuple(
                        SealSnapshotSeason(
                            competition_season_id=(
                                season.identity.competition_season_id
                            ),
                            role=season.role,
                            through_week=season.through_week,
                        )
                        for season in inputs.seasons
                    ),
                    artifact=receipt,
                    completeness_warnings=materialized.completeness_warnings,
                ),
            )
        except Exception as error:
            self._fail_claimed(claimed.id, error)
            public_error = self._public_failure(claimed.id, error)
            if public_error is error:
                raise
            raise public_error from error
        finally:
            if materialized is not None:
                try:
                    materialized.path.unlink(missing_ok=True)
                except OSError:
                    pass
        return self._reuse_ready(inputs, sealed)

    def _replay(
        self,
        inputs: ResolvedSnapshotInputs,
        payloads: tuple[VerifiedPayload, ...],
    ) -> tuple[SnapshotEndpointRecords, ...]:
        if len(payloads) != len(inputs.manifest.entries):
            raise DatalayerScopeConflict(
                "resolved snapshot payload count does not match the frozen manifest"
            )
        requirements = {
            entry.request.scope_key: entry for entry in inputs.requirements.entries
        }
        replayed = []
        for manifest_entry, payload in zip(
            inputs.manifest.entries,
            payloads,
            strict=True,
        ):
            if (
                payload.request_id != manifest_entry.request_id
                or payload.scope_key != manifest_entry.scope_key
                or payload.sha256 != manifest_entry.response_sha256
            ):
                raise DatalayerScopeConflict(
                    "resolved snapshot payload does not match the frozen manifest"
                )
            replayed.append(
                SnapshotEndpointRecords(
                    manifest_entry=manifest_entry,
                    records=normalize_snapshot_payload(
                        self._payload_value(payload),
                        requirements[manifest_entry.scope_key],
                    ),
                )
            )
        return tuple(replayed)

    def _payload_value(self, payload: VerifiedPayload) -> JsonValue:
        if isinstance(payload, InlineVerifiedPayload):
            return payload.payload
        if isinstance(payload, ObjectVerifiedPayload):
            artifact = self._files.open_verified(
                payload.storage_key,
                expected_sha256=payload.sha256,
                expected_byte_length=payload.byte_length,
            )
            return parse_json_bytes(artifact.path.read_bytes())
        assert_never(payload)

    def _wait_for_existing(
        self,
        inputs: ResolvedSnapshotInputs,
        building: DataSnapshot,
    ) -> ReadyDataSnapshot | None:
        deadline = self._monotonic() + self._wait_timeout
        while True:
            stale_before = self._clock() - timedelta(seconds=self._stale_after)
            if self._snapshots.fail_stale_build(building.build_key, stale_before):
                return None
            current = self._snapshots.get(building.id)
            if current.status is SnapshotStatus.READY:
                return self._reuse_ready(inputs, current)
            if current.status in {SnapshotStatus.FAILED, SnapshotStatus.EXPIRED}:
                return None
            if self._monotonic() >= deadline:
                raise SnapshotUnavailable(
                    "snapshot build did not finish within the wait budget"
                )
            self._delay(self._poll_interval)

    def _reuse_ready(
        self,
        inputs: ResolvedSnapshotInputs,
        snapshot: DataSnapshot,
    ) -> ReadyDataSnapshot | None:
        if snapshot.status is not SnapshotStatus.READY or snapshot.artifact is None:
            raise DatalayerScopeConflict("snapshot is not a sealed ready artifact")
        _validate_ready_identity(inputs, snapshot, self._projection_version)
        try:
            artifact = self._files.open_verified(
                snapshot.artifact.storage_key,
                expected_sha256=snapshot.artifact.sha256,
                expected_byte_length=snapshot.artifact.byte_length,
            )
            requests = self._snapshots.list_requests(snapshot.id)
            verify_sealed_snapshot_file(artifact.path, snapshot, requests)
        except (LocalArtifactVerificationError, SnapshotArtifactInvalid):
            self._snapshots.expire_unusable(
                snapshot.id,
                ArtifactFailure(
                    code="snapshot_artifact_unusable",
                    summary="Snapshot artifact is missing, corrupt, or inconsistent",
                ),
            )
            return None
        return _ready_snapshot(snapshot, artifact)

    def _fail_claimed(self, snapshot_id: UUID, error: Exception) -> None:
        if isinstance(error, SnapshotUnavailable):
            code = "snapshot_inputs_unavailable"
            summary = error.message
        elif isinstance(error, SnapshotArtifactInvalid):
            code = "snapshot_artifact_invalid"
            summary = "Snapshot artifact validation failed"
        elif isinstance(error, DatalayerError):
            code = "snapshot_build_rejected"
            summary = str(error)
        elif isinstance(error, LocalArtifactVerificationError):
            code = "snapshot_artifact_invalid"
            summary = "Snapshot artifact verification failed"
        else:
            code = "snapshot_build_failed"
            summary = "Snapshot build failed unexpectedly"
        self._snapshots.mark_failed(
            snapshot_id,
            SnapshotFailure(code=code, summary=summary[:500]),
        )

    @staticmethod
    def _public_failure(snapshot_id: UUID, error: Exception) -> Exception:
        if isinstance(error, DatalayerError):
            return error
        if isinstance(error, LocalArtifactVerificationError):
            return SnapshotUnavailable("selected snapshot payload is unavailable")
        return InternalDatalayerFailure(str(snapshot_id))


def _validate_ready_identity(
    inputs: ResolvedSnapshotInputs,
    snapshot: DataSnapshot,
    projection_version: str,
) -> None:
    if (
        snapshot.primary_competition_season_id
        != inputs.primary.competition_season_id
        or snapshot.through_week != inputs.primary.through_week
        or snapshot.as_of_date != inputs.primary.as_of_date
        or snapshot.snapshot_projection_version != projection_version
        or snapshot.input_revision != inputs.input_revision
    ):
        raise DatalayerScopeConflict(
            "ready snapshot identity conflicts with resolved inputs"
        )
    expected = tuple(
        (
            season.identity.competition_id,
            season.identity.competition_season_id,
            season.identity.sleeper_league_id,
            season.identity.season_year,
            season.identity.sequence_number,
            season.role,
            season.through_week,
        )
        for season in inputs.seasons
    )
    actual = tuple(
        (
            season.competition_id,
            season.competition_season_id,
            season.sleeper_league_id,
            season.season_year,
            season.sequence_number,
            season.role,
            season.through_week,
        )
        for season in snapshot.included_seasons
    )
    if actual != expected:
        raise DatalayerScopeConflict(
            "ready snapshot season membership conflicts with resolved inputs"
        )


def _ready_snapshot(
    snapshot: DataSnapshot,
    artifact: VerifiedLocalArtifact,
) -> ReadyDataSnapshot:
    return ReadyDataSnapshot(
        id=snapshot.id,
        competition_id=snapshot.competition_id,
        primary_competition_season_id=snapshot.primary_competition_season_id,
        through_week=snapshot.through_week,
        as_of_date=snapshot.as_of_date,
        build_key=snapshot.build_key,
        snapshot_projection_version=snapshot.snapshot_projection_version,
        artifact=artifact,
        completeness_warnings=snapshot.completeness_warnings,
        input_revision=snapshot.input_revision,
        included_seasons=tuple(
            ReadySnapshotSeason(
                competition_season_id=season.competition_season_id,
                sleeper_league_id=season.sleeper_league_id,
                season_year=season.season_year,
                sequence_number=season.sequence_number,
                role=season.role.value,
                through_week=season.through_week,
            )
            for season in snapshot.included_seasons
        ),
    )


def _nonblank(value: str, name: str) -> str:
    normalized = value.strip()
    if not normalized or normalized != value:
        raise ValueError(f"{name} must not be empty")
    return value


def _positive_number(value: float, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{name} must be positive")
    return float(value)


__all__ = [
    "DatalayerResolvedSnapshotBuilder",
    "canonical_resolved_snapshot_build_key",
]
