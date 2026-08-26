"""Competition-scoped atomic snapshot identity and lifecycle manager."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.database.models.core import CompetitionSeason
from backend.database.models.sleeper import ApiRequest as StoredApiRequest
from backend.database.models.sleeper import DataSnapshot as StoredDataSnapshot
from backend.database.models.sleeper import (
    DataSnapshotRequest as StoredSnapshotRequest,
)
from backend.database.models.sleeper import DataSnapshotSeason as StoredSnapshotSeason
from backend.database.models.sleeper import RefreshRun as StoredRefreshRun
from backend.database.sessions import (
    SessionFactory,
    read_only_session,
    transaction_session,
)
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.sleeper_data.snapshots.objects import (
    ArtifactFailure,
    BeginSnapshotBuild,
    ClaimedSnapshotBuild,
    DataSnapshot,
    DataSnapshotPage,
    DataSnapshotQuery,
    ExistingBuildingSnapshot,
    ExistingReadySnapshot,
    SealSnapshot,
    SealSnapshotSeason,
    SnapshotBuildState,
    SnapshotFailure,
    SnapshotRequestMembership,
    SnapshotSeasonMembership,
    SnapshotSeasonRole,
)
from backend.services.datalayer.contracts import (
    CompletenessWarning,
    RequestStatus,
    SnapshotSelectionRole,
    SnapshotStatus,
)
from backend.services.datalayer.errors import (
    DatalayerResourceNotFound,
    DatalayerScopeConflict,
)
from backend.services.datalayer.local_files import StoredLocalArtifact
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


_ACTIVE_STATUSES = (SnapshotStatus.BUILDING.value, SnapshotStatus.READY.value)
_GLOBAL_ENDPOINTS = {EndpointKind.NFL_STATE, EndpointKind.PLAYER_CATALOG}


class DataSnapshotManager:
    """Own snapshot claims, terminal transitions, and exact membership."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id

    def begin_or_get(self, command: BeginSnapshotBuild) -> SnapshotBuildState:
        with transaction_session(self._session_factory) as session:
            season = self._require_season(session, command.competition_season_id)
            snapshot_id = uuid4()
            statement = (
                pg_insert(StoredDataSnapshot)
                .values(
                    id=snapshot_id,
                    competition_id=self._competition_id,
                    primary_competition_season_id=season.id,
                    build_key=command.build_key,
                    input_revision=command.input_revision,
                    domain_cutoff_week=command.through_week,
                    domain_cutoff_at=None,
                    as_of_date=command.as_of_date,
                    status=SnapshotStatus.BUILDING.value,
                    snapshot_projection_version=command.snapshot_projection_version,
                    code_version=command.code_version,
                    completeness_warnings=[],
                    failure_summary=None,
                    sqlite_artifact_sha256=None,
                    sqlite_artifact_byte_length=None,
                    sqlite_artifact_storage_key=None,
                )
                .on_conflict_do_nothing(
                    index_elements=[StoredDataSnapshot.build_key],
                    index_where=StoredDataSnapshot.status.in_(_ACTIVE_STATUSES),
                )
            )
            inserted_id = session.scalar(
                statement.returning(StoredDataSnapshot.id)
            )
            stored = session.scalar(
                sa.select(StoredDataSnapshot).where(
                    StoredDataSnapshot.build_key == command.build_key,
                    StoredDataSnapshot.status.in_(_ACTIVE_STATUSES),
                )
            )
            if stored is None:
                raise RuntimeError("snapshot claim did not produce an active row")
            self._validate_identity(stored, command)
            memberships = (
                self._load_season_memberships(session, [stored.id]).get(stored.id, ())
                if stored.status == SnapshotStatus.READY.value
                else ()
            )
            snapshot = _decode_snapshot(stored, memberships)
            if inserted_id == snapshot_id and stored.id == snapshot_id:
                return ClaimedSnapshotBuild(snapshot=snapshot)
            if snapshot.status is SnapshotStatus.BUILDING:
                return ExistingBuildingSnapshot(snapshot=snapshot)
            return ExistingReadySnapshot(snapshot=snapshot)

    def seal_ready(self, snapshot_id: UUID, command: SealSnapshot) -> DataSnapshot:
        with transaction_session(self._session_factory) as session:
            stored = self._load(session, snapshot_id, lock=True)
            if stored.status != SnapshotStatus.BUILDING.value:
                raise DatalayerScopeConflict(
                    "only the current building snapshot can be sealed"
                )
            season_rows = self._resolve_seal_seasons(session, stored, command.seasons)
            allowed_seasons = {season.id for season, _ in season_rows}
            self._validate_membership(
                session,
                stored,
                command.requests,
                allowed_seasons=allowed_seasons,
            )
            session.execute(
                sa.insert(StoredSnapshotRequest),
                [
                    {
                        "data_snapshot_id": stored.id,
                        "api_request_id": membership.request_id,
                        "scope_key": membership.scope_key.value,
                        "response_sha256": membership.response_sha256,
                        "selection_role": membership.selection_role.value,
                    }
                    for membership in command.requests
                ],
            )
            session.execute(
                sa.insert(StoredSnapshotSeason),
                [
                    {
                        "data_snapshot_id": stored.id,
                        "competition_id": self._competition_id,
                        "primary_competition_season_id": (
                            stored.primary_competition_season_id
                        ),
                        "competition_season_id": season.id,
                        "role": membership.role.value,
                        "through_week": membership.through_week,
                    }
                    for season, membership in season_rows
                ],
            )
            stored.status = SnapshotStatus.READY.value
            stored.completeness_warnings = [
                _encode_warning(warning) for warning in command.completeness_warnings
            ]
            stored.failure_summary = None
            stored.sqlite_artifact_sha256 = command.artifact.sha256
            stored.sqlite_artifact_byte_length = command.artifact.byte_length
            stored.sqlite_artifact_storage_key = command.artifact.storage_key
            stored.completed_at = sa.func.now()
            session.flush()
            memberships = self._load_season_memberships(session, [stored.id])[stored.id]
            return _decode_snapshot(stored, memberships)

    def mark_failed(
        self,
        snapshot_id: UUID,
        failure: SnapshotFailure,
    ) -> DataSnapshot:
        with transaction_session(self._session_factory) as session:
            stored = self._load(session, snapshot_id, lock=True)
            if stored.status == SnapshotStatus.FAILED.value:
                return _decode_snapshot(stored)
            if stored.status != SnapshotStatus.BUILDING.value:
                raise DatalayerScopeConflict(
                    "only a building snapshot can be marked failed"
                )
            stored.status = SnapshotStatus.FAILED.value
            stored.failure_summary = failure.model_dump(mode="json")
            stored.completed_at = sa.func.now()
            session.flush()
            return _decode_snapshot(stored)

    def fail_stale_build(self, build_key: str, stale_before: datetime) -> bool:
        failure = SnapshotFailure(
            code="snapshot_build_stale",
            summary="Snapshot build exceeded the stale threshold",
        )
        with transaction_session(self._session_factory) as session:
            result = session.execute(
                sa.update(StoredDataSnapshot)
                .where(
                    StoredDataSnapshot.competition_id == self._competition_id,
                    StoredDataSnapshot.build_key == build_key,
                    StoredDataSnapshot.status == SnapshotStatus.BUILDING.value,
                    StoredDataSnapshot.created_at < stale_before,
                )
                .values(
                    status=SnapshotStatus.FAILED.value,
                    failure_summary=failure.model_dump(mode="json"),
                    completed_at=sa.func.now(),
                )
                .execution_options(synchronize_session=False)
            )
            return cast(int, result.rowcount) == 1

    def expire_unusable(
        self,
        snapshot_id: UUID,
        failure: ArtifactFailure,
    ) -> DataSnapshot:
        del failure  # sealed ready metadata cannot persist an expiration reason
        with transaction_session(self._session_factory) as session:
            stored = self._load(session, snapshot_id, lock=True)
            if stored.status == SnapshotStatus.EXPIRED.value:
                memberships = self._load_season_memberships(session, [stored.id]).get(
                    stored.id, ()
                )
                return _decode_snapshot(stored, memberships)
            if stored.status != SnapshotStatus.READY.value:
                raise DatalayerScopeConflict(
                    "only a ready snapshot can be expired as unusable"
                )
            stored.status = SnapshotStatus.EXPIRED.value
            session.flush()
            memberships = self._load_season_memberships(session, [stored.id]).get(
                stored.id, ()
            )
            return _decode_snapshot(stored, memberships)

    def get(self, snapshot_id: UUID) -> DataSnapshot:
        with read_only_session(self._session_factory) as session:
            stored = self._load(session, snapshot_id)
            memberships = self._load_season_memberships(session, [stored.id]).get(
                stored.id, ()
            )
            return _decode_snapshot(stored, memberships)

    def list_snapshots(self, query: DataSnapshotQuery) -> DataSnapshotPage:
        with read_only_session(self._session_factory) as session:
            self._require_season(session, query.competition_season_id)
            where = sa.and_(
                StoredDataSnapshot.competition_id == self._competition_id,
                StoredDataSnapshot.primary_competition_season_id
                == query.competition_season_id,
            )
            total = cast(
                int,
                session.scalar(
                    sa.select(sa.func.count())
                    .select_from(StoredDataSnapshot)
                    .where(where)
                ),
            )
            rows = session.scalars(
                sa.select(StoredDataSnapshot)
                .where(where)
                .order_by(
                    StoredDataSnapshot.created_at.desc(),
                    StoredDataSnapshot.id.desc(),
                )
                .limit(query.limit)
                .offset(query.offset)
            ).all()
            memberships = self._load_season_memberships(
                session, [snapshot.id for snapshot in rows]
            )
            return DataSnapshotPage(
                items=tuple(
                    _decode_snapshot(row, memberships.get(row.id, ())) for row in rows
                ),
                total=total,
                limit=query.limit,
                offset=query.offset,
            )

    def list_requests(
        self,
        snapshot_id: UUID,
    ) -> tuple[SnapshotRequestMembership, ...]:
        with read_only_session(self._session_factory) as session:
            self._load(session, snapshot_id)
            rows = session.execute(
                sa.select(StoredSnapshotRequest, StoredApiRequest.endpoint_kind)
                .join(
                    StoredApiRequest,
                    StoredApiRequest.id == StoredSnapshotRequest.api_request_id,
                )
                .where(StoredSnapshotRequest.data_snapshot_id == snapshot_id)
            ).all()
            memberships = [
                SnapshotRequestMembership(
                    request_id=row.api_request_id,
                    endpoint_kind=EndpointKind(endpoint_kind),
                    scope_key=ScopeKey.parse(row.scope_key),
                    response_sha256=row.response_sha256,
                    selection_role=SnapshotSelectionRole(row.selection_role),
                )
                for row, endpoint_kind in rows
            ]
            return tuple(sorted(memberships, key=_membership_order))

    def _load(
        self,
        session: Session,
        snapshot_id: UUID,
        *,
        lock: bool = False,
    ) -> StoredDataSnapshot:
        statement = sa.select(StoredDataSnapshot).where(
            StoredDataSnapshot.id == snapshot_id,
            StoredDataSnapshot.competition_id == self._competition_id,
        )
        if lock:
            statement = statement.with_for_update()
        stored = session.scalar(statement)
        if stored is None:
            raise DatalayerResourceNotFound("data_snapshot", str(snapshot_id))
        return stored

    def _require_season(
        self,
        session: Session,
        season_id: UUID,
    ) -> CompetitionSeason:
        season = session.scalar(
            sa.select(CompetitionSeason).where(
                CompetitionSeason.id == season_id,
                CompetitionSeason.competition_id == self._competition_id,
            )
        )
        if season is None:
            raise DatalayerResourceNotFound("competition_season", str(season_id))
        return season

    @staticmethod
    def _validate_identity(
        stored: StoredDataSnapshot,
        command: BeginSnapshotBuild,
    ) -> None:
        if (
            stored.primary_competition_season_id != command.competition_season_id
            or stored.domain_cutoff_week != command.through_week
            or stored.domain_cutoff_at is not None
            or stored.as_of_date != command.as_of_date
            or stored.snapshot_projection_version
            != command.snapshot_projection_version
            or stored.input_revision != command.input_revision
        ):
            raise DatalayerScopeConflict(
                "active snapshot build key conflicts with its canonical identity"
            )

    def _validate_membership(
        self,
        session: Session,
        snapshot: StoredDataSnapshot,
        memberships: tuple[SnapshotRequestMembership, ...],
        *,
        allowed_seasons: set[UUID],
    ) -> None:
        request_ids = [membership.request_id for membership in memberships]
        rows = session.execute(
            sa.select(StoredApiRequest, StoredRefreshRun.competition_id)
            .join(
                StoredRefreshRun,
                StoredRefreshRun.id == StoredApiRequest.refresh_run_id,
            )
            .where(StoredApiRequest.id.in_(request_ids))
        ).all()
        by_id = {
            request.id: (request, competition_id)
            for request, competition_id in rows
        }
        for membership in memberships:
            stored = by_id.get(membership.request_id)
            if stored is None:
                raise DatalayerScopeConflict(
                    "snapshot membership references an unavailable request"
                )
            request, request_competition_id = stored
            endpoint_kind = EndpointKind(request.endpoint_kind)
            if (
                request.status != RequestStatus.SUCCEEDED.value
                or not request.is_complete
                or request.payload_id is None
                or request.response_sha256 != membership.response_sha256
                or request.scope_key != membership.scope_key.value
                or endpoint_kind is not membership.endpoint_kind
            ):
                raise DatalayerScopeConflict(
                    "snapshot membership request is not eligible"
                )
            if endpoint_kind in _GLOBAL_ENDPOINTS:
                if request.competition_season_id is not None:
                    raise DatalayerScopeConflict(
                        "global snapshot membership unexpectedly belongs to a season"
                    )
            elif (
                request.competition_season_id not in allowed_seasons
                or request_competition_id != self._competition_id
            ):
                raise DatalayerScopeConflict(
                    "snapshot membership belongs to another competition scope"
                )

    def _resolve_seal_seasons(
        self,
        session: Session,
        snapshot: StoredDataSnapshot,
        requested: tuple[SealSnapshotSeason, ...],
    ) -> tuple[tuple[CompetitionSeason, SealSnapshotSeason], ...]:
        explicit = bool(requested)
        memberships = requested or (
            SealSnapshotSeason(
                competition_season_id=snapshot.primary_competition_season_id,
                role=SnapshotSeasonRole.PRIMARY,
                through_week=cast(int, snapshot.domain_cutoff_week),
            ),
        )
        season_ids = [membership.competition_season_id for membership in memberships]
        seasons = session.scalars(
            sa.select(CompetitionSeason).where(
                CompetitionSeason.competition_id == self._competition_id,
                CompetitionSeason.id.in_(season_ids),
            )
        ).all()
        by_id = {season.id: season for season in seasons}
        if set(by_id) != set(season_ids):
            raise DatalayerScopeConflict(
                "snapshot season membership belongs to another competition"
            )
        primary_membership = next(
            (
                membership
                for membership in memberships
                if membership.role is SnapshotSeasonRole.PRIMARY
            ),
            None,
        )
        if (
            primary_membership is None
            or primary_membership.competition_season_id
            != snapshot.primary_competition_season_id
            or primary_membership.through_week != snapshot.domain_cutoff_week
        ):
            raise DatalayerScopeConflict(
                "snapshot primary season membership conflicts with its identity"
            )
        primary = by_id[snapshot.primary_competition_season_id]
        for membership in memberships:
            season = by_id[membership.competition_season_id]
            if membership.role is SnapshotSeasonRole.HISTORY and (
                season.sequence_number >= primary.sequence_number
                or membership.through_week != 18
            ):
                raise DatalayerScopeConflict(
                    "snapshot historical season membership is invalid"
                )
        if explicit:
            expected = set(
                session.scalars(
                    sa.select(CompetitionSeason.id).where(
                        CompetitionSeason.competition_id == self._competition_id,
                        CompetitionSeason.sequence_number <= primary.sequence_number,
                    )
                )
            )
            if set(season_ids) != expected:
                raise DatalayerScopeConflict(
                    "snapshot season membership must contain every predecessor"
                )
        return tuple(
            sorted(
                ((by_id[item.competition_season_id], item) for item in memberships),
                key=lambda pair: pair[0].sequence_number,
            )
        )

    def _load_season_memberships(
        self,
        session: Session,
        snapshot_ids: list[UUID],
    ) -> dict[UUID, tuple[SnapshotSeasonMembership, ...]]:
        if not snapshot_ids:
            return {}
        rows = session.execute(
            sa.select(StoredSnapshotSeason, CompetitionSeason)
            .join(
                CompetitionSeason,
                CompetitionSeason.id == StoredSnapshotSeason.competition_season_id,
            )
            .where(StoredSnapshotSeason.data_snapshot_id.in_(snapshot_ids))
            .order_by(
                StoredSnapshotSeason.data_snapshot_id,
                CompetitionSeason.sequence_number,
            )
        ).all()
        grouped: dict[UUID, list[SnapshotSeasonMembership]] = {
            snapshot_id: [] for snapshot_id in snapshot_ids
        }
        for stored, season in rows:
            grouped[stored.data_snapshot_id].append(
                SnapshotSeasonMembership(
                    competition_id=stored.competition_id,
                    competition_season_id=season.id,
                    sleeper_league_id=season.sleeper_league_id,
                    season_year=season.season_year,
                    sequence_number=season.sequence_number,
                    role=SnapshotSeasonRole(stored.role),
                    through_week=stored.through_week,
                )
            )
        return {key: tuple(value) for key, value in grouped.items()}


def _decode_snapshot(
    stored: StoredDataSnapshot,
    included_seasons: tuple[SnapshotSeasonMembership, ...] = (),
) -> DataSnapshot:
    artifact_values = (
        stored.sqlite_artifact_storage_key,
        stored.sqlite_artifact_sha256,
        stored.sqlite_artifact_byte_length,
    )
    artifact: StoredLocalArtifact | None
    if all(value is None for value in artifact_values):
        artifact = None
    elif all(value is not None for value in artifact_values):
        artifact = StoredLocalArtifact(
            storage_key=cast(str, stored.sqlite_artifact_storage_key),
            sha256=cast(str, stored.sqlite_artifact_sha256),
            byte_length=cast(int, stored.sqlite_artifact_byte_length),
        )
    else:
        raise RuntimeError("stored snapshot has a partial artifact receipt")
    failure = (
        None
        if stored.failure_summary is None
        else SnapshotFailure.model_validate(stored.failure_summary)
    )
    return DataSnapshot(
        id=stored.id,
        competition_id=stored.competition_id,
        primary_competition_season_id=stored.primary_competition_season_id,
        build_key=stored.build_key,
        input_revision=stored.input_revision,
        through_week=cast(int, stored.domain_cutoff_week),
        as_of_date=stored.as_of_date,
        status=SnapshotStatus(stored.status),
        snapshot_projection_version=stored.snapshot_projection_version,
        code_version=stored.code_version,
        completeness_warnings=tuple(
            _decode_warning(value) for value in stored.completeness_warnings
        ),
        failure=failure,
        artifact=artifact,
        included_seasons=included_seasons,
        created_at=stored.created_at,
        completed_at=stored.completed_at,
    )


def _encode_warning(warning: CompletenessWarning) -> dict[str, Any]:
    return {
        "code": warning.code,
        "summary": warning.summary,
        "scope_key": (
            None if warning.scope_key is None else warning.scope_key.value
        ),
    }


def _decode_warning(value: dict[str, Any]) -> CompletenessWarning:
    raw_scope = value.get("scope_key")
    return CompletenessWarning(
        code=value["code"],
        summary=value["summary"],
        scope_key=None if raw_scope is None else ScopeKey.parse(raw_scope),
    )


def _membership_order(
    membership: SnapshotRequestMembership,
) -> tuple[int, int, str]:
    parts = membership.scope_key.value.split(":")
    week = int(parts[-1]) if parts[-1].isdigit() else 0
    base_order = {
        SnapshotSelectionRole.LEAGUE: 0,
        SnapshotSelectionRole.LEAGUE_USERS: 1,
        SnapshotSelectionRole.NFL_STATE: 2,
        SnapshotSelectionRole.PLAYER_CATALOG: 3,
        SnapshotSelectionRole.LEAGUE_ROSTERS: 4,
        SnapshotSelectionRole.TRADED_PICKS: 5,
    }
    if membership.selection_role in base_order:
        return 0, base_order[membership.selection_role], membership.scope_key.value
    if membership.selection_role is SnapshotSelectionRole.WEEK_MATCHUPS:
        return 1, week * 2, membership.scope_key.value
    if membership.selection_role is SnapshotSelectionRole.WEEK_TRANSACTIONS:
        return 1, week * 2 + 1, membership.scope_key.value
    if membership.selection_role is SnapshotSelectionRole.WINNERS_BRACKET:
        return 2, 0, membership.scope_key.value
    return 2, 1, membership.scope_key.value
