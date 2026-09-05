"""Daily snapshot claim, selection, replay, and sealing workflow."""

from __future__ import annotations

from collections.abc import Callable, Collection
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
from time import monotonic, sleep
from typing import Annotated, Protocol, assert_never
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from backend.resources._contracts import ContractModel
from backend.resources.sleeper_data.league_seasons import SnapshotPlanningContext
from backend.resources.sleeper_data.requests import (
    ApiRequestCandidate,
    InlineVerifiedPayload,
    ObjectVerifiedPayload,
    SnapshotCandidateQuery,
    VerifiedPayload,
)
from backend.resources.sleeper_data.rosters import SeasonRosterIdentity
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
)
from backend.services.datalayer.canonical_json import JsonValue, parse_json_bytes
from backend.services.datalayer.contracts import (
    CompletenessWarning,
    ReadyDataSnapshot,
    ReadySnapshotSeason,
    SnapshotRequest,
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
from backend.services.datalayer.snapshot_selection import (
    SelectedRequestManifest,
    SelectedRequestManifestEntry,
    SnapshotRequirement,
    SnapshotRequirements,
    canonical_snapshot_build_key,
    plan_snapshot_requirements,
    select_snapshot_requests,
)
from backend.services.datalayer.snapshot_replay import normalize_snapshot_payload
from backend.services.datalayer.sleeper.endpoints import (
    EndpointRecords,
    LeagueRostersEndpointRecords,
)
from backend.services.datalayer.sleeper.scope import ScopeKey
from backend.services.datalayer.versions import SNAPSHOT_PROJECTION_VERSION


Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
WallClock = Callable[[], datetime]
MonotonicClock = Callable[[], float]


class SnapshotPlanningReader(Protocol):
    def get_snapshot_planning_context(
        self, competition_season_id: UUID
    ) -> SnapshotPlanningContext: ...


class SnapshotRequestReader(Protocol):
    def list_snapshot_candidates(
        self,
        query: SnapshotCandidateQuery,
    ) -> tuple[ApiRequestCandidate, ...]: ...

    def resolve_verified_payloads(
        self,
        request_ids: Collection[UUID],
    ) -> tuple[VerifiedPayload, ...]: ...


class SnapshotRosterIdentityReader(Protocol):
    def list_roster_identities(
        self,
        competition_season_id: UUID,
    ) -> tuple[SeasonRosterIdentity, ...]: ...


class SnapshotLifecycle(Protocol):
    def begin_or_get(self, command: BeginSnapshotBuild) -> SnapshotBuildState: ...

    def seal_ready(self, snapshot_id: UUID, command: SealSnapshot) -> DataSnapshot: ...

    def mark_failed(
        self, snapshot_id: UUID, failure: SnapshotFailure
    ) -> DataSnapshot: ...

    def fail_stale_build(self, build_key: str, stale_before: datetime) -> bool: ...

    def expire_unusable(
        self, snapshot_id: UUID, failure: ArtifactFailure
    ) -> DataSnapshot: ...

    def get(self, snapshot_id: UUID) -> DataSnapshot: ...


class SnapshotFileStore(Protocol):
    def store_file(
        self, kind: LocalArtifactKind, source: Path
    ) -> StoredLocalArtifact: ...

    def open_verified(
        self,
        storage_key: str,
        *,
        expected_sha256: str,
        expected_byte_length: int,
    ) -> VerifiedLocalArtifact: ...


class SnapshotEndpointRecords(ContractModel):
    manifest_entry: SelectedRequestManifestEntry
    records: EndpointRecords

    @model_validator(mode="after")
    def validate_endpoint(self) -> "SnapshotEndpointRecords":
        if self.records.endpoint_kind is not self.manifest_entry.endpoint_kind:
            raise ValueError("snapshot records do not match their manifest endpoint")
        return self


class SnapshotMaterializationInput(ContractModel):
    request: SnapshotRequest
    planning_context: SnapshotPlanningContext
    build_key: Sha256
    snapshot_projection_version: str
    manifest: SelectedRequestManifest
    endpoint_records: tuple[SnapshotEndpointRecords, ...]
    roster_identities: tuple[SeasonRosterIdentity, ...]

    @model_validator(mode="after")
    def validate_records(self) -> "SnapshotMaterializationInput":
        manifest_ids = [entry.request_id for entry in self.manifest.entries]
        record_ids = [
            entry.manifest_entry.request_id for entry in self.endpoint_records
        ]
        if record_ids != manifest_ids:
            raise ValueError("snapshot endpoint records must follow manifest order")
        expected_scope = (
            self.planning_context.competition_id,
            self.planning_context.competition_season_id,
        )
        if any(
            (
                identity.competition_id,
                identity.competition_season_id,
            )
            != expected_scope
            for identity in self.roster_identities
        ):
            raise ValueError("snapshot roster identities must match the planning scope")
        _require_distinct(
            [identity.sleeper_roster_id for identity in self.roster_identities],
            "Sleeper roster IDs",
        )
        _require_distinct(
            [identity.season_roster_id for identity in self.roster_identities],
            "season-roster IDs",
        )
        _require_distinct(
            [identity.franchise_id for identity in self.roster_identities],
            "franchise IDs",
        )
        selected_roster_ids = tuple(
            roster.sleeper_roster_id
            for endpoint in self.endpoint_records
            if isinstance(endpoint.records, LeagueRostersEndpointRecords)
            for roster in endpoint.records.rosters
        )
        if (
            len(selected_roster_ids) != len(set(selected_roster_ids))
            or set(selected_roster_ids)
            != {identity.sleeper_roster_id for identity in self.roster_identities}
        ):
            raise ValueError(
                "snapshot roster identities must exactly match selected rosters"
            )
        return self


class MaterializedSnapshot(ContractModel):
    path: Path
    sha256: Sha256
    byte_length: int = Field(strict=True, ge=0)
    completeness_warnings: tuple[CompletenessWarning, ...] = ()

    @model_validator(mode="after")
    def validate_path(self) -> "MaterializedSnapshot":
        if not self.path.is_absolute():
            raise ValueError("materialized snapshot path must be absolute")
        return self


class SnapshotMaterializer(Protocol):
    def materialize(
        self,
        materialization: SnapshotMaterializationInput,
    ) -> MaterializedSnapshot: ...


class DatalayerSnapshotService:
    """Resolve one healthy ready snapshot for a daily factual identity."""

    def __init__(
        self,
        *,
        planning: SnapshotPlanningReader,
        roster_identities: SnapshotRosterIdentityReader,
        requests: SnapshotRequestReader,
        snapshots: SnapshotLifecycle,
        materializer: SnapshotMaterializer,
        files: SnapshotFileStore,
        code_version: str,
        snapshot_projection_version: str = SNAPSHOT_PROJECTION_VERSION,
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
        self._wait_timeout = _positive_number(
            wait_timeout_seconds, "wait_timeout_seconds"
        )
        self._stale_after = _positive_number(
            stale_after_seconds, "stale_after_seconds"
        )
        self._poll_interval = _positive_number(
            poll_interval_seconds, "poll_interval_seconds"
        )
        self._planning = planning
        self._roster_identities = roster_identities
        self._requests = requests
        self._snapshots = snapshots
        self._materializer = materializer
        self._files = files
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic_clock
        self._delay = delay

    def get_or_create(self, request: SnapshotRequest) -> ReadyDataSnapshot:
        build_key = canonical_snapshot_build_key(request, self._projection_version)
        command = BeginSnapshotBuild(
            competition_season_id=request.competition_season_id,
            through_week=request.through_week,
            as_of_date=request.as_of_date,
            build_key=build_key,
            snapshot_projection_version=self._projection_version,
            code_version=self._code_version,
        )
        while True:
            state = self._snapshots.begin_or_get(command)
            if isinstance(state, ClaimedSnapshotBuild):
                ready = self._build_claimed(request, state.snapshot)
                if ready is not None:
                    return ready
                continue
            if isinstance(state, ExistingReadySnapshot):
                ready = self._reuse_ready(state.snapshot)
                if ready is not None:
                    return ready
                continue
            if isinstance(state, ExistingBuildingSnapshot):
                ready = self._wait_for_existing(state.snapshot)
                if ready is not None:
                    return ready
                continue
            assert_never(state)

    def _build_claimed(
        self,
        request: SnapshotRequest,
        claimed: DataSnapshot,
    ) -> ReadyDataSnapshot | None:
        materialized: MaterializedSnapshot | None = None
        try:
            context = self._planning.get_snapshot_planning_context(
                request.competition_season_id
            )
            roster_identities = self._roster_identities.list_roster_identities(
                request.competition_season_id
            )
            requirements = plan_snapshot_requirements(request, context)
            candidates = self._requests.list_snapshot_candidates(
                SnapshotCandidateQuery(
                    competition_season_id=request.competition_season_id,
                    scope_keys=requirements.scope_keys,
                    through_week=request.through_week,
                )
            )
            manifest = select_snapshot_requests(request, requirements, candidates)
            payloads = self._requests.resolve_verified_payloads(
                [entry.request_id for entry in manifest.entries]
            )
            records = self._replay(requirements, manifest, payloads)
            materialized = self._materializer.materialize(
                SnapshotMaterializationInput(
                    request=request,
                    planning_context=context,
                    build_key=claimed.build_key,
                    snapshot_projection_version=self._projection_version,
                    manifest=manifest,
                    endpoint_records=records,
                    roster_identities=roster_identities,
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
                        for entry in manifest.entries
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
        return self._reuse_ready(sealed)

    def _replay(
        self,
        requirements: SnapshotRequirements,
        manifest: SelectedRequestManifest,
        payloads: tuple[VerifiedPayload, ...],
    ) -> tuple[SnapshotEndpointRecords, ...]:
        if len(payloads) != len(manifest.entries):
            raise DatalayerScopeConflict(
                "resolved snapshot payload count does not match the manifest"
            )
        requirements_by_scope = {
            entry.request.scope_key: entry for entry in requirements.entries
        }
        replayed: list[SnapshotEndpointRecords] = []
        for manifest_entry, payload in zip(manifest.entries, payloads, strict=True):
            if (
                payload.request_id != manifest_entry.request_id
                or payload.scope_key != manifest_entry.scope_key
                or payload.sha256 != manifest_entry.response_sha256
            ):
                raise DatalayerScopeConflict(
                    "resolved snapshot payload does not match the manifest"
                )
            requirement = requirements_by_scope[manifest_entry.scope_key]
            replayed.append(
                SnapshotEndpointRecords(
                    manifest_entry=manifest_entry,
                    records=normalize_snapshot_payload(
                        self._payload_value(payload),
                        requirement,
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
        building: DataSnapshot,
    ) -> ReadyDataSnapshot | None:
        deadline = self._monotonic() + self._wait_timeout
        while True:
            stale_before = self._clock() - timedelta(seconds=self._stale_after)
            if self._snapshots.fail_stale_build(building.build_key, stale_before):
                return None
            current = self._snapshots.get(building.id)
            if current.status is SnapshotStatus.READY:
                return self._reuse_ready(current)
            if current.status in {SnapshotStatus.FAILED, SnapshotStatus.EXPIRED}:
                return None
            if self._monotonic() >= deadline:
                raise SnapshotUnavailable(
                    "snapshot build did not finish within the wait budget"
                )
            self._delay(self._poll_interval)

    def _reuse_ready(self, snapshot: DataSnapshot) -> ReadyDataSnapshot | None:
        if snapshot.status is not SnapshotStatus.READY or snapshot.artifact is None:
            raise DatalayerScopeConflict("snapshot is not a sealed ready artifact")
        try:
            artifact = self._files.open_verified(
                snapshot.artifact.storage_key,
                expected_sha256=snapshot.artifact.sha256,
                expected_byte_length=snapshot.artifact.byte_length,
            )
        except LocalArtifactVerificationError:
            self._snapshots.expire_unusable(
                snapshot.id,
                ArtifactFailure(
                    code="snapshot_artifact_unusable",
                    summary="Snapshot artifact is missing or corrupt",
                ),
            )
            return None
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

    def _fail_claimed(self, snapshot_id: UUID, error: Exception) -> None:
        if isinstance(error, SnapshotUnavailable):
            code = "snapshot_inputs_unavailable"
            summary = error.message
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


def _require_distinct(values: list[object], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"snapshot roster identities contain duplicate {label}")
