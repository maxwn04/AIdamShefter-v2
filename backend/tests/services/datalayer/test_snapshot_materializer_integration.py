from datetime import date
from pathlib import Path

from sqlalchemy.engine import Engine

from backend.database.sessions import create_session_factory
from backend.resources.sleeper_data import (
    ApiRequestManager,
    DataSnapshotManager,
    LeagueSeasonManager,
    NormalizedScopeManager,
    RefreshRunManager,
    RosterManager,
)
from backend.services.datalayer import (
    DatalayerSnapshotService,
    LocalDatalayerFileStore,
    RefreshRequest,
    RefreshTrigger,
    SQLiteSnapshotMaterializer,
    SnapshotRequest,
)
from backend.services.datalayer.refresh_service import DatalayerRefreshService
from backend.tests.database.conftest import database_engine, migrated_database
from backend.tests.resources.sleeper_data.conftest import (
    manager_context,
    seed_domain,
)
from backend.tests.services.datalayer.test_refresh_service_integration import (
    FixtureSource,
)


def test_refresh_to_materialization_and_atomic_seal(
    database_engine: Engine,
    tmp_path: Path,
) -> None:
    domain = seed_domain(database_engine, label="Snapshot Materializer")
    context = manager_context(domain)
    sessions = create_session_factory(database_engine)
    files = LocalDatalayerFileStore(tmp_path / "data")
    requests = ApiRequestManager(sessions, context)
    planning = LeagueSeasonManager(sessions, context)
    snapshots = DataSnapshotManager(sessions, context)
    refresh = DatalayerRefreshService(
        source=FixtureSource(domain),
        identities=planning,
        refreshes=RefreshRunManager(sessions, context),
        attempts=requests,
        scopes=NormalizedScopeManager(sessions, context),
        files=files,
        code_version="test",
        delay=lambda _: None,
    )
    refresh.refresh(
        RefreshRequest(
            competition_season_id=domain.season_id,
            through_week=1,
            trigger=RefreshTrigger.MANUAL,
        )
    )
    service = DatalayerSnapshotService(
        planning=planning,
        roster_identities=RosterManager(sessions, context),
        requests=requests,
        snapshots=snapshots,
        materializer=SQLiteSnapshotMaterializer(tmp_path / "staging"),
        files=files,
        code_version="test",
    )

    ready = service.get_or_create(
        SnapshotRequest(
            competition_season_id=domain.season_id,
            through_week=1,
            as_of_date=date(2026, 9, 8),
        )
    )

    memberships = snapshots.list_requests(ready.id)
    assert ready.artifact.path.exists()
    assert ready.artifact.path.read_bytes().startswith(b"SQLite format 3")
    assert len(memberships) == 10
    assert len({item.scope_key for item in memberships}) == 10
    assert all(len(item.response_sha256) == 64 for item in memberships)
    assert list((tmp_path / "staging").glob("*.sqlite")) == []
