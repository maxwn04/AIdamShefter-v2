"""Exercise automatic claim persistence against real PostgreSQL constraints."""

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.sessions import SessionFactory
from backend.resources.sleeper_data.refreshes import RefreshRunManager
from backend.resources.sleeper_data.refreshes.automatic import AutomaticRefreshClaimManager
from backend.resources.sleeper_data.refreshes.objects import (
    AutomaticRefreshFailure,
    ClaimAutomaticRefresh,
    CompleteAutomaticRefresh,
)
from backend.services.datalayer.contracts import RefreshStatus
from backend.services.datalayer.sleeper.endpoints import build_league_request
from backend.tests.resources.sleeper_data.conftest import (
    Domain,
    manager_context,
    start_refresh,
)


def test_claim_join_complete_and_failure_null_semantics(
    database_engine: Engine,
    session_factory: SessionFactory,
    domain: Domain,
    refresh_manager: RefreshRunManager,
) -> None:
    manager = AutomaticRefreshClaimManager(session_factory, manager_context(domain))
    command = ClaimAutomaticRefresh(
        competition_season_id=domain.season_id,
        active_key="a" * 64,
        requested_through_week=18,
        policy_version="test",
        reason="missing",
        coverage_fingerprint="b" * 64,
    )
    winner = manager.begin_or_get(command)
    assert winner.kind == "claimed"
    joined = manager.begin_or_get(command)
    assert joined.kind == "existing"
    assert joined.claim.id == winner.claim.id

    def assert_sql_null(claim_id: UUID) -> None:
        with database_engine.connect() as connection:
            assert connection.scalar(
                sa.text(
                    "SELECT failure_summary IS NULL "
                    "FROM sleeper.automatic_refresh_claims WHERE id = :id"
                ),
                {"id": claim_id},
            ) is True

    assert_sql_null(winner.claim.id)
    run = start_refresh(
        refresh_manager,
        domain,
        build_league_request(domain.season_id, domain.sleeper_league_id),
        requested_through_week=18,
    )
    completed = manager.complete(
        winner.claim.id,
        CompleteAutomaticRefresh(
            refresh_run_id=run.id, refresh_status=RefreshStatus.SUCCEEDED,
        ),
    )
    assert completed.status == "completed"
    assert completed.failure is None
    assert_sql_null(completed.id)

    replacement = manager.begin_or_get(command)
    assert replacement.kind == "claimed"
    failure = AutomaticRefreshFailure(
        code="source_unavailable", summary="Source unavailable",
    )
    failed = manager.fail(replacement.claim.id, failure)
    assert failed.status == "failed"
    assert manager.get(failed.id).failure == failure
