from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.core import CompetitionSeason
from backend.database.models.sleeper import ApiRequest as StoredApiRequest
from backend.database.models.sleeper import RefreshRun as StoredRefreshRun
from backend.database.sessions import SessionFactory, create_session_factory
from backend.resources.sleeper_data.refreshes import (
    RefreshRunManager,
    RefreshRunQuery,
)
from backend.resources.sleeper_data.requests import (
    ApiRequest,
    ApiRequestManager,
    RecordApiAttempt,
)
from backend.services.datalayer.contracts import (
    NormalizationStatus,
    RefreshStatus,
)
from backend.services.datalayer.errors import DatalayerResourceNotFound
from backend.services.datalayer.sleeper.endpoints import (
    build_league_request,
    build_league_users_request,
)
from backend.services.datalayer.sleeper.endpoints.contracts import CompletenessFinding
from backend.services.datalayer.sleeper.responses import EndpointRequest
from backend.tests.resources.sleeper_data.conftest import (
    Domain,
    failed_attempt,
    manager_context,
    seed_domain,
    start_refresh,
    successful_attempt,
)


def _record_success(
    manager: ApiRequestManager,
    refresh_id: UUID,
    endpoint: EndpointRequest,
    requested_at: datetime,
) -> ApiRequest:
    request = manager.record_attempt(
        RecordApiAttempt(
            refresh_run_id=refresh_id,
            attempt=successful_attempt(
                endpoint,
                {"observed_at": requested_at.isoformat()},
                requested_at=requested_at,
            ),
            completeness=CompletenessFinding(is_complete=True),
        )
    )
    return request


def _record_failure(
    manager: ApiRequestManager,
    refresh_id: UUID,
    endpoint: EndpointRequest,
    requested_at: datetime,
) -> None:
    manager.record_attempt(
        RecordApiAttempt(
            refresh_run_id=refresh_id,
            attempt=failed_attempt(endpoint, requested_at=requested_at),
            completeness=CompletenessFinding(
                is_complete=False,
                reason="source_attempt_failed",
            ),
        )
    )


def _mark_normalized(session_factory: SessionFactory, request_id: UUID) -> None:
    with session_factory.begin() as session:
        session.execute(
            sa.update(StoredApiRequest)
            .where(StoredApiRequest.id == request_id)
            .values(
                normalization_status=NormalizationStatus.SUCCEEDED.value,
                normalizer_version="test-normalizer",
                normalized_at=datetime.now(UTC),
            )
        )


def _managers(
    database_engine: Engine,
    domain: Domain,
) -> tuple[RefreshRunManager, ApiRequestManager, SessionFactory]:
    session_factory = create_session_factory(database_engine)
    context = manager_context(domain)
    return (
        RefreshRunManager(session_factory, context),
        ApiRequestManager(session_factory, context),
        session_factory,
    )


def test_refresh_run_is_competition_scoped(
    database_engine: Engine,
    domain: Domain,
    refresh_manager: RefreshRunManager,
) -> None:
    other = seed_domain(database_engine, label="Other")
    other_refresh_manager, _, _ = _managers(database_engine, other)
    endpoint = build_league_request(domain.season_id, domain.sleeper_league_id)
    refresh = start_refresh(refresh_manager, domain, endpoint)

    assert refresh_manager.get_refresh(refresh.id) == refresh
    with pytest.raises(DatalayerResourceNotFound):
        other_refresh_manager.get_refresh(refresh.id)
    with pytest.raises(DatalayerResourceNotFound):
        start_refresh(other_refresh_manager, domain, endpoint)


def test_refresh_history_is_season_scoped_newest_first_and_paginated(
    database_engine: Engine,
    domain: Domain,
    refresh_manager: RefreshRunManager,
) -> None:
    other_season_id = uuid4()
    other_league_id = f"league-{other_season_id}"
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(CompetitionSeason),
            {
                "id": other_season_id,
                "competition_id": domain.competition_id,
                "season_year": 2027,
                "sequence_number": 2,
                "sleeper_league_id": other_league_id,
            },
        )
    endpoint = build_league_request(domain.season_id, domain.sleeper_league_id)
    first = start_refresh(refresh_manager, domain, endpoint)
    second = start_refresh(refresh_manager, domain, endpoint)
    other_domain = Domain(
        competition_id=domain.competition_id,
        season_id=other_season_id,
        sleeper_league_id=other_league_id,
        franchise_ids=domain.franchise_ids,
        roster_ids=domain.roster_ids,
    )
    other_endpoint = build_league_request(other_season_id, other_league_id)
    other = start_refresh(refresh_manager, other_domain, other_endpoint)
    tied_at = datetime(2026, 8, 23, 12, tzinfo=UTC)
    with database_engine.begin() as connection:
        connection.execute(
            sa.update(StoredRefreshRun)
            .where(StoredRefreshRun.id.in_([first.id, second.id]))
            .values(started_at=tied_at)
        )

    expected = sorted((first.id, second.id), reverse=True)
    first_page = refresh_manager.list_refreshes(
        RefreshRunQuery(
            competition_season_id=domain.season_id,
            limit=1,
        )
    )
    second_page = refresh_manager.list_refreshes(
        RefreshRunQuery(
            competition_season_id=domain.season_id,
            limit=1,
            offset=1,
        )
    )

    assert first_page.total == 2
    assert [first_page.items[0].id, second_page.items[0].id] == expected
    assert refresh_manager.get_refresh_for_season(domain.season_id, first.id).id == (
        first.id
    )
    with pytest.raises(DatalayerResourceNotFound):
        refresh_manager.get_refresh_for_season(domain.season_id, other.id)
    with pytest.raises(DatalayerResourceNotFound):
        refresh_manager.list_refreshes(
            RefreshRunQuery(competition_season_id=uuid4())
        )


def test_finish_refresh_uses_latest_attempt_and_optional_failures_do_not_downgrade(
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
    session_factory: SessionFactory,
) -> None:
    league = build_league_request(domain.season_id, domain.sleeper_league_id)
    users = build_league_users_request(domain.season_id, domain.sleeper_league_id)
    now = datetime.now(UTC)
    refresh = start_refresh(
        refresh_manager,
        domain,
        league,
        users,
        required={users.scope_key.value: False},
    )
    league_request = _record_success(request_manager, refresh.id, league, now)
    _mark_normalized(session_factory, league_request.id)
    _record_failure(request_manager, refresh.id, users, now + timedelta(seconds=1))

    finished = refresh_manager.finish_refresh(refresh.id)

    assert finished.status is RefreshStatus.SUCCEEDED
    assert (
        finished.request_count,
        finished.succeeded_request_count,
        finished.failed_request_count,
    ) == (2, 1, 1)
    assert finished.error == {
        "code": "refresh_scopes_failed",
        "scope_keys": [users.scope_key.value],
    }
    assert refresh_manager.finish_refresh(refresh.id) == finished


def test_finish_refresh_derives_partial_and_failed_required_plans(
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
    session_factory: SessionFactory,
) -> None:
    league = build_league_request(domain.season_id, domain.sleeper_league_id)
    users = build_league_users_request(domain.season_id, domain.sleeper_league_id)
    now = datetime.now(UTC)

    partial = start_refresh(refresh_manager, domain, league, users)
    good = _record_success(request_manager, partial.id, league, now)
    _mark_normalized(session_factory, good.id)
    _record_failure(request_manager, partial.id, users, now + timedelta(seconds=1))
    assert refresh_manager.finish_refresh(partial.id).status is RefreshStatus.PARTIAL

    failed = start_refresh(refresh_manager, domain, league)
    first = _record_success(
        request_manager,
        failed.id,
        league,
        now + timedelta(seconds=2),
    )
    _mark_normalized(session_factory, first.id)
    _record_failure(
        request_manager,
        failed.id,
        league,
        now + timedelta(seconds=3),
    )
    outcome = refresh_manager.finish_refresh(failed.id)
    assert outcome.status is RefreshStatus.FAILED
    assert (outcome.succeeded_request_count, outcome.failed_request_count) == (0, 1)


def test_finish_stale_running_is_bounded_scoped_and_uses_durable_attempts(
    database_engine: Engine,
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
    session_factory: SessionFactory,
) -> None:
    league = build_league_request(domain.season_id, domain.sleeper_league_id)
    users = build_league_users_request(domain.season_id, domain.sleeper_league_id)
    cutoff = datetime(2026, 8, 23, 12, tzinfo=UTC)

    failed = start_refresh(refresh_manager, domain, league)
    partial = start_refresh(refresh_manager, domain, league, users)
    succeeded = start_refresh(refresh_manager, domain, league)
    recent = start_refresh(refresh_manager, domain, league)
    terminal = start_refresh(refresh_manager, domain, league)

    partial_request = _record_success(
        request_manager,
        partial.id,
        league,
        cutoff - timedelta(hours=1),
    )
    _mark_normalized(session_factory, partial_request.id)
    _record_failure(
        request_manager,
        partial.id,
        users,
        cutoff - timedelta(minutes=59),
    )
    succeeded_request = _record_success(
        request_manager,
        succeeded.id,
        league,
        cutoff - timedelta(minutes=30),
    )
    _mark_normalized(session_factory, succeeded_request.id)
    refresh_manager.finish_refresh(terminal.id)

    other = seed_domain(database_engine, label="Other stale refresh")
    other_manager, _, _ = _managers(database_engine, other)
    other_endpoint = build_league_request(
        other.season_id,
        other.sleeper_league_id,
    )
    other_refresh = start_refresh(other_manager, other, other_endpoint)

    started_at = {
        failed.id: cutoff - timedelta(hours=4),
        partial.id: cutoff - timedelta(hours=3),
        succeeded.id: cutoff - timedelta(hours=2),
        recent.id: cutoff,
        terminal.id: cutoff - timedelta(hours=5),
        other_refresh.id: cutoff - timedelta(hours=6),
    }
    with database_engine.begin() as connection:
        for refresh_id, timestamp in started_at.items():
            connection.execute(
                sa.update(StoredRefreshRun)
                .where(StoredRefreshRun.id == refresh_id)
                .values(started_at=timestamp)
            )

    first_batch = refresh_manager.finish_stale_running(
        stale_before=cutoff,
        limit=2,
    )

    assert [refresh.id for refresh in first_batch] == [failed.id, partial.id]
    assert [refresh.status for refresh in first_batch] == [
        RefreshStatus.FAILED,
        RefreshStatus.PARTIAL,
    ]
    assert first_batch[0].error == {
        "code": "refresh_scopes_failed",
        "scope_keys": [league.scope_key.value],
    }
    assert (
        first_batch[1].request_count,
        first_batch[1].succeeded_request_count,
        first_batch[1].failed_request_count,
    ) == (2, 1, 1)

    second_batch = refresh_manager.finish_stale_running(
        stale_before=cutoff,
        limit=2,
    )

    assert [refresh.id for refresh in second_batch] == [succeeded.id]
    assert second_batch[0].status is RefreshStatus.SUCCEEDED
    assert second_batch[0].completed_at is not None
    assert refresh_manager.get_refresh(recent.id).status is RefreshStatus.RUNNING
    assert other_manager.get_refresh(other_refresh.id).status is RefreshStatus.RUNNING
    assert refresh_manager.finish_stale_running(stale_before=cutoff, limit=2) == ()


@pytest.mark.parametrize("limit", [0, 201])
def test_finish_stale_running_validates_cutoff_and_limit(
    refresh_manager: RefreshRunManager,
    limit: int,
) -> None:
    with pytest.raises(ValueError, match="limit"):
        refresh_manager.finish_stale_running(
            stale_before=datetime.now(UTC),
            limit=limit,
        )

    with pytest.raises(ValueError, match="timezone-aware"):
        refresh_manager.finish_stale_running(
            stale_before=datetime.now(),
            limit=1,
        )
