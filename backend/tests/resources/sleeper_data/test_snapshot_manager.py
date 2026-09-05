from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.core import CompetitionSeason
from backend.database.models.sleeper import DataSnapshot as StoredDataSnapshot
from backend.database.models.sleeper import DataSnapshotRequest
from backend.database.sessions import create_session_factory
from backend.resources.sleeper_data import (
    ApiRequestManager,
    ArtifactFailure,
    BeginSnapshotBuild,
    ClaimedSnapshotBuild,
    DataSnapshotManager,
    DataSnapshotQuery,
    ExistingBuildingSnapshot,
    ExistingReadySnapshot,
    RefreshRunManager,
    SealSnapshot,
    SealSnapshotSeason,
    SnapshotFailure,
    SnapshotRequestMembership,
    SnapshotSeasonRole,
)
from backend.services.datalayer import (
    DatalayerResourceNotFound,
    DatalayerScopeConflict,
    EndpointKind,
    SnapshotSelectionRole,
    SnapshotStatus,
)
from backend.services.datalayer.local_files import StoredLocalArtifact
from backend.services.datalayer.sleeper.endpoints import build_league_request
from backend.tests.resources.sleeper_data.conftest import (
    Domain,
    manager_context,
    record_complete_attempt,
    seed_domain,
    start_refresh,
)


def _command(domain: Domain, *, build_key: str = "a" * 64) -> BeginSnapshotBuild:
    return BeginSnapshotBuild(
        competition_season_id=domain.season_id,
        through_week=8,
        as_of_date=date(2026, 10, 27),
        build_key=build_key,
        snapshot_projection_version="1",
        code_version="test",
    )


def _artifact(value: str = "b") -> StoredLocalArtifact:
    sha256 = value * 64
    return StoredLocalArtifact(
        storage_key=f"snapshots/sha256/{sha256[:2]}/{sha256}.sqlite",
        sha256=sha256,
        byte_length=5,
    )


def _request_membership(
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
) -> SnapshotRequestMembership:
    endpoint = build_league_request(domain.season_id, domain.sleeper_league_id)
    refresh = start_refresh(refresh_manager, domain, endpoint)
    request = record_complete_attempt(
        request_manager,
        refresh.id,
        endpoint,
        {"league_id": domain.sleeper_league_id},
    )
    return SnapshotRequestMembership(
        request_id=request.id,
        endpoint_kind=EndpointKind.LEAGUE,
        scope_key=endpoint.scope_key,
        response_sha256=request.response_sha256,
        selection_role=SnapshotSelectionRole.LEAGUE,
    )


def test_claim_seal_and_reuse_preserve_exact_membership(
    domain: Domain,
    snapshot_manager: DataSnapshotManager,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
) -> None:
    command = _command(domain)
    claimed = snapshot_manager.begin_or_get(command)
    assert isinstance(claimed, ClaimedSnapshotBuild)
    building = snapshot_manager.begin_or_get(command)
    assert isinstance(building, ExistingBuildingSnapshot)
    assert building.snapshot.id == claimed.snapshot.id
    membership = _request_membership(domain, refresh_manager, request_manager)

    sealed = snapshot_manager.seal_ready(
        claimed.snapshot.id,
        SealSnapshot(requests=(membership,), artifact=_artifact()),
    )

    assert sealed.status is SnapshotStatus.READY
    assert sealed.artifact == _artifact()
    assert snapshot_manager.list_requests(sealed.id) == (membership,)
    ready = snapshot_manager.begin_or_get(command)
    assert isinstance(ready, ExistingReadySnapshot)
    assert ready.snapshot == sealed


def test_multi_season_seal_accepts_historical_request_membership(
    database_engine: Engine,
    domain: Domain,
    snapshot_manager: DataSnapshotManager,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
) -> None:
    primary_season_id = uuid4()
    primary_league_id = f"league-{primary_season_id}"
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(CompetitionSeason),
            {
                "id": primary_season_id,
                "competition_id": domain.competition_id,
                "season_year": 2027,
                "sequence_number": 2,
                "sleeper_league_id": primary_league_id,
            },
        )
    primary = Domain(
        competition_id=domain.competition_id,
        season_id=primary_season_id,
        sleeper_league_id=primary_league_id,
        franchise_ids=domain.franchise_ids,
        roster_ids=domain.roster_ids,
    )
    claimed = snapshot_manager.begin_or_get(
        _command(primary, build_key="9" * 64)
    )
    assert isinstance(claimed, ClaimedSnapshotBuild)
    historical_request = _request_membership(
        domain,
        refresh_manager,
        request_manager,
    )
    primary_request = _request_membership(
        primary,
        refresh_manager,
        request_manager,
    )

    sealed = snapshot_manager.seal_ready(
        claimed.snapshot.id,
        SealSnapshot(
            requests=(historical_request, primary_request),
            seasons=(
                SealSnapshotSeason(
                    competition_season_id=domain.season_id,
                    role=SnapshotSeasonRole.HISTORY,
                    through_week=18,
                ),
                SealSnapshotSeason(
                    competition_season_id=primary.season_id,
                    role=SnapshotSeasonRole.PRIMARY,
                    through_week=8,
                ),
            ),
            artifact=_artifact("9"),
        ),
    )

    assert [season.competition_season_id for season in sealed.included_seasons] == [
        domain.season_id,
        primary.season_id,
    ]
    assert [season.role for season in sealed.included_seasons] == [
        SnapshotSeasonRole.HISTORY,
        SnapshotSeasonRole.PRIMARY,
    ]
    assert set(snapshot_manager.list_requests(sealed.id)) == {
        historical_request,
        primary_request,
    }


def test_concurrent_claims_converge_on_one_active_snapshot(
    domain: Domain,
    snapshot_manager: DataSnapshotManager,
) -> None:
    command = _command(domain, build_key="c" * 64)

    with ThreadPoolExecutor(max_workers=2) as pool:
        states = tuple(
            pool.map(lambda _: snapshot_manager.begin_or_get(command), range(2))
        )

    assert {state.kind for state in states} == {"claimed", "building"}
    assert len({state.snapshot.id for state in states}) == 1


def test_failed_and_stale_builds_release_the_daily_key_and_reject_late_seal(
    database_engine: Engine,
    domain: Domain,
    snapshot_manager: DataSnapshotManager,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
) -> None:
    command = _command(domain, build_key="d" * 64)
    first = snapshot_manager.begin_or_get(command)
    assert isinstance(first, ClaimedSnapshotBuild)
    failed = snapshot_manager.mark_failed(
        first.snapshot.id,
        SnapshotFailure(code="fixture_failed", summary="Fixture failure"),
    )
    assert failed.status is SnapshotStatus.FAILED
    replacement = snapshot_manager.begin_or_get(command)
    assert isinstance(replacement, ClaimedSnapshotBuild)
    assert replacement.snapshot.id != first.snapshot.id
    with database_engine.begin() as connection:
        connection.execute(
            sa.update(StoredDataSnapshot)
            .where(StoredDataSnapshot.id == replacement.snapshot.id)
            .values(created_at=datetime.now(UTC) - timedelta(minutes=10))
        )
    assert snapshot_manager.fail_stale_build(
        command.build_key,
        datetime.now(UTC) - timedelta(minutes=5),
    )
    newest = snapshot_manager.begin_or_get(command)
    assert isinstance(newest, ClaimedSnapshotBuild)
    membership = _request_membership(domain, refresh_manager, request_manager)
    with pytest.raises(DatalayerScopeConflict, match="current building"):
        snapshot_manager.seal_ready(
            replacement.snapshot.id,
            SealSnapshot(requests=(membership,), artifact=_artifact("e")),
        )


def test_invalid_membership_rolls_back_without_partial_rows(
    database_engine: Engine,
    domain: Domain,
    snapshot_manager: DataSnapshotManager,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
) -> None:
    claimed = snapshot_manager.begin_or_get(_command(domain, build_key="f" * 64))
    assert isinstance(claimed, ClaimedSnapshotBuild)
    membership = _request_membership(domain, refresh_manager, request_manager)
    invalid = membership.model_copy(update={"response_sha256": "0" * 64})

    with pytest.raises(DatalayerScopeConflict, match="eligible"):
        snapshot_manager.seal_ready(
            claimed.snapshot.id,
            SealSnapshot(requests=(invalid,), artifact=_artifact("1")),
        )

    assert snapshot_manager.get(claimed.snapshot.id).status is SnapshotStatus.BUILDING
    with database_engine.connect() as connection:
        count = connection.scalar(
            sa.select(sa.func.count())
            .select_from(DataSnapshotRequest)
            .where(DataSnapshotRequest.data_snapshot_id == claimed.snapshot.id)
        )
    assert count == 0


def test_expired_ready_snapshot_releases_key_but_remains_auditable(
    domain: Domain,
    snapshot_manager: DataSnapshotManager,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
) -> None:
    command = _command(domain, build_key="2" * 64)
    claimed = snapshot_manager.begin_or_get(command)
    assert isinstance(claimed, ClaimedSnapshotBuild)
    membership = _request_membership(domain, refresh_manager, request_manager)
    ready = snapshot_manager.seal_ready(
        claimed.snapshot.id,
        SealSnapshot(requests=(membership,), artifact=_artifact("3")),
    )
    expired = snapshot_manager.expire_unusable(
        ready.id,
        ArtifactFailure(code="artifact_missing", summary="Artifact is missing"),
    )
    replacement = snapshot_manager.begin_or_get(command)

    assert expired.status is SnapshotStatus.EXPIRED
    assert expired.artifact == ready.artifact
    assert snapshot_manager.list_requests(expired.id) == (membership,)
    assert isinstance(replacement, ClaimedSnapshotBuild)
    assert replacement.snapshot.id != expired.id


def test_snapshot_reads_are_competition_scoped(
    database_engine: Engine,
    domain: Domain,
    snapshot_manager: DataSnapshotManager,
) -> None:
    claimed = snapshot_manager.begin_or_get(_command(domain, build_key="4" * 64))
    assert isinstance(claimed, ClaimedSnapshotBuild)
    other = seed_domain(database_engine, label="Other snapshot")
    other_manager = DataSnapshotManager(
        create_session_factory(database_engine),
        manager_context(other),
    )

    with pytest.raises(DatalayerResourceNotFound):
        other_manager.get(claimed.snapshot.id)
    with pytest.raises(DatalayerResourceNotFound):
        other_manager.list_requests(claimed.snapshot.id)


def test_snapshot_history_is_season_scoped_newest_first_and_paginated(
    database_engine: Engine,
    domain: Domain,
    snapshot_manager: DataSnapshotManager,
) -> None:
    other_season_id = uuid4()
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(CompetitionSeason),
            {
                "id": other_season_id,
                "competition_id": domain.competition_id,
                "season_year": 2027,
                "sequence_number": 2,
                "sleeper_league_id": f"league-{other_season_id}",
            },
        )
    first = snapshot_manager.begin_or_get(_command(domain, build_key="5" * 64))
    second = snapshot_manager.begin_or_get(_command(domain, build_key="6" * 64))
    assert isinstance(first, ClaimedSnapshotBuild)
    assert isinstance(second, ClaimedSnapshotBuild)
    snapshot_manager.mark_failed(
        first.snapshot.id,
        SnapshotFailure(code="fixture_failed", summary="Fixture failure"),
    )
    other_domain = Domain(
        competition_id=domain.competition_id,
        season_id=other_season_id,
        sleeper_league_id=f"league-{other_season_id}",
        franchise_ids=domain.franchise_ids,
        roster_ids=domain.roster_ids,
    )
    other = snapshot_manager.begin_or_get(_command(other_domain, build_key="7" * 64))
    assert isinstance(other, ClaimedSnapshotBuild)
    tied_at = datetime(2026, 8, 23, 12, tzinfo=UTC)
    with database_engine.begin() as connection:
        connection.execute(
            sa.update(StoredDataSnapshot)
            .where(StoredDataSnapshot.id.in_([first.snapshot.id, second.snapshot.id]))
            .values(created_at=tied_at)
        )

    expected = sorted((first.snapshot.id, second.snapshot.id), reverse=True)
    first_page = snapshot_manager.list_snapshots(
        DataSnapshotQuery(
            competition_season_id=domain.season_id,
            limit=1,
        )
    )
    second_page = snapshot_manager.list_snapshots(
        DataSnapshotQuery(
            competition_season_id=domain.season_id,
            limit=1,
            offset=1,
        )
    )

    assert first_page.total == 2
    assert [first_page.items[0].id, second_page.items[0].id] == expected
    assert {first_page.items[0].status, second_page.items[0].status} == {
        SnapshotStatus.BUILDING,
        SnapshotStatus.FAILED,
    }
    assert snapshot_manager.list_snapshots(
        DataSnapshotQuery(competition_season_id=other_season_id)
    ).items[0].id == other.snapshot.id
    with pytest.raises(DatalayerResourceNotFound):
        snapshot_manager.list_snapshots(
            DataSnapshotQuery(competition_season_id=uuid4())
        )
