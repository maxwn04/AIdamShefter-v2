"""Reusable PostgreSQL fixtures for Sleeper resource-manager tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.core import (
    Competition,
    CompetitionSeason,
    Franchise,
    SeasonRoster,
)
from backend.database.sessions import SessionFactory, create_session_factory
from backend.resources.context import (
    CompetitionScope,
    ManagerContext,
    SystemProcessActor,
)
from backend.resources.sleeper_data.refreshes import (
    PlannedEndpointScope,
    RefreshRun,
    RefreshRunManager,
    StartRefresh,
)
from backend.resources.sleeper_data.normalized_scopes import NormalizedScopeManager
from backend.resources.sleeper_data.requests import (
    ApiRequest,
    ApiRequestManager,
    RecordApiAttempt,
)
from backend.services.datalayer.canonical_json import JsonValue, canonical_json_bytes
from backend.services.datalayer.contracts import RefreshTrigger, RequestStatus
from backend.services.datalayer.sleeper.responses import (
    EndpointRequest,
    FailedSourceAttempt,
    SanitizedSourceError,
    SuccessfulSourceAttempt,
)
from backend.services.datalayer.sleeper.endpoints import (
    build_league_request,
    build_league_rosters_request,
    build_league_users_request,
    build_matchups_request,
    build_player_catalog_request,
    build_transactions_request,
)
from backend.services.datalayer.sleeper.endpoints.contracts import (
    CompletenessFinding,
    LeagueEndpointRecords,
    LeagueRecord,
    LeagueRostersEndpointRecords,
    LeagueUserRecord,
    LeagueUsersEndpointRecords,
    MatchupRecord,
    MatchupsEndpointRecords,
    PlayerCatalogEndpointRecords,
    PlayerPerformanceRecord,
    PlayerRecord,
    RosterManagerRecord,
    RosterPlayerRecord,
    RosterRecord,
    TransactionMoveRecord,
    TransactionRecord,
    TransactionsEndpointRecords,
    UserRecord,
)
from backend.tests.database.conftest import database_engine, migrated_database


@pytest.fixture(autouse=True)
def clean_sleeper_resources(request: pytest.FixtureRequest) -> None:
    """Start every Sleeper resource test with no aggregate or domain rows."""

    if "database_engine" not in request.fixturenames:
        return
    database_engine = request.getfixturevalue("database_engine")
    with database_engine.begin() as connection:
        connection.execute(sa.text("""
                TRUNCATE TABLE core.competitions,
                    sleeper.api_payloads CASCADE
                """))


@dataclass(frozen=True)
class Domain:
    competition_id: UUID
    season_id: UUID
    sleeper_league_id: str
    franchise_ids: tuple[UUID, UUID]
    roster_ids: tuple[UUID, UUID]


@dataclass(frozen=True)
class ProjectedSeason:
    """Representative current state shared by resource read-manager tests."""

    domain: Domain
    refresh_run_id: UUID
    league_request_id: UUID
    users_request_id: UUID
    player_request_id: UUID
    roster_request_id: UUID
    matchup_request_id: UUID
    transaction_request_id: UUID
    week: int
    user_ids: tuple[str, str]
    player_ids: tuple[str, str, str, str]
    sleeper_transaction_id: str


def seed_domain(database_engine: Engine, *, label: str = "Sleeper Resource") -> Domain:
    """Seed the competition identities shared by audit, projection, and read tests."""

    competition_id = uuid4()
    season_id = uuid4()
    franchise_ids = (uuid4(), uuid4())
    roster_ids = (uuid4(), uuid4())
    sleeper_league_id = f"league-{season_id}"
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            {"id": competition_id, "display_name": f"{label} League"},
        )
        connection.execute(
            sa.insert(CompetitionSeason),
            {
                "id": season_id,
                "competition_id": competition_id,
                "season_year": 2026,
                "sequence_number": 1,
                "sleeper_league_id": sleeper_league_id,
            },
        )
        connection.execute(
            sa.insert(Franchise),
            [
                {
                    "id": franchise_ids[index],
                    "competition_id": competition_id,
                    "display_name": f"{label} Team {index + 1}",
                }
                for index in range(2)
            ],
        )
        connection.execute(
            sa.insert(SeasonRoster),
            [
                {
                    "id": roster_ids[index],
                    "competition_id": competition_id,
                    "competition_season_id": season_id,
                    "franchise_id": franchise_ids[index],
                    "sleeper_roster_id": str(index + 1),
                }
                for index in range(2)
            ],
        )
    return Domain(
        competition_id=competition_id,
        season_id=season_id,
        sleeper_league_id=sleeper_league_id,
        franchise_ids=franchise_ids,
        roster_ids=roster_ids,
    )


def manager_context(domain: Domain) -> ManagerContext[CompetitionScope]:
    return ManagerContext[CompetitionScope](
        actor=SystemProcessActor(process_name="sleeper-resource-test"),
        scope=CompetitionScope(competition_id=domain.competition_id),
        correlation_id=uuid4(),
    )


def successful_attempt(
    endpoint: EndpointRequest,
    payload: JsonValue,
    *,
    requested_at: datetime | None = None,
) -> SuccessfulSourceAttempt:
    requested_at = requested_at or datetime.now(UTC)
    content = canonical_json_bytes(payload)
    return SuccessfulSourceAttempt(
        endpoint=endpoint,
        requested_at=requested_at,
        completed_at=requested_at + timedelta(milliseconds=5),
        latency_ms=5,
        http_status=200,
        payload=payload,
        raw_sha256=hashlib.sha256(content).hexdigest(),
        byte_length=len(content),
    )


def failed_attempt(
    endpoint: EndpointRequest,
    *,
    requested_at: datetime | None = None,
    status: RequestStatus = RequestStatus.TRANSPORT_ERROR,
) -> FailedSourceAttempt:
    requested_at = requested_at or datetime.now(UTC)
    return FailedSourceAttempt(
        endpoint=endpoint,
        requested_at=requested_at,
        completed_at=requested_at + timedelta(milliseconds=5),
        latency_ms=5,
        status=status,
        http_status=500 if status is RequestStatus.HTTP_ERROR else None,
        error=SanitizedSourceError(code="source_failed", summary="source failed"),
    )


def record_complete_attempt(
    manager: ApiRequestManager,
    refresh_id: UUID,
    endpoint: EndpointRequest,
    payload: JsonValue,
    *,
    requested_at: datetime | None = None,
) -> ApiRequest:
    """Record one complete successful observation for later projection tests."""

    return manager.record_attempt(
        RecordApiAttempt(
            refresh_run_id=refresh_id,
            attempt=successful_attempt(
                endpoint,
                payload,
                requested_at=requested_at,
            ),
            completeness=CompletenessFinding(is_complete=True),
        )
    )


def start_refresh(
    manager: RefreshRunManager,
    domain: Domain,
    *endpoints: EndpointRequest,
    requested_through_week: int | None = None,
    required: dict[str, bool] | None = None,
) -> RefreshRun:
    required = required or {}
    return manager.start_refresh(
        StartRefresh(
            competition_season_id=domain.season_id,
            requested_through_week=requested_through_week,
            trigger=RefreshTrigger.MANUAL,
            endpoint_scope=tuple(
                PlannedEndpointScope(
                    scope_key=endpoint.scope_key,
                    endpoint_kind=endpoint.endpoint_kind,
                    required=required.get(endpoint.scope_key.value, True),
                )
                for endpoint in endpoints
            ),
            code_version="test",
            normalizer_version="test-normalizer",
        )
    )


@pytest.fixture
def domain(database_engine: Engine) -> Domain:
    return seed_domain(database_engine)


@pytest.fixture
def session_factory(database_engine: Engine) -> SessionFactory:
    return create_session_factory(database_engine)


@pytest.fixture
def refresh_manager(
    session_factory: SessionFactory,
    domain: Domain,
) -> RefreshRunManager:
    return RefreshRunManager(session_factory, manager_context(domain))


@pytest.fixture
def request_manager(
    session_factory: SessionFactory,
    domain: Domain,
) -> ApiRequestManager:
    return ApiRequestManager(session_factory, manager_context(domain))


@pytest.fixture
def normalized_scope_manager(
    session_factory: SessionFactory,
    domain: Domain,
) -> NormalizedScopeManager:
    return NormalizedScopeManager(session_factory, manager_context(domain))


@pytest.fixture
def projected_season(
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
    normalized_scope_manager: NormalizedScopeManager,
) -> ProjectedSeason:
    """Apply a small, complete league graph through the public write boundary."""

    week = 1
    endpoints = (
        build_league_request(domain.season_id, domain.sleeper_league_id),
        build_league_users_request(domain.season_id, domain.sleeper_league_id),
        build_player_catalog_request(),
        build_league_rosters_request(domain.season_id, domain.sleeper_league_id),
        build_matchups_request(domain.season_id, domain.sleeper_league_id, week),
        build_transactions_request(domain.season_id, domain.sleeper_league_id, week),
    )
    refresh = start_refresh(
        refresh_manager,
        domain,
        *endpoints,
        requested_through_week=week,
    )
    now = datetime.now(UTC)
    requests = tuple(
        record_complete_attempt(
            request_manager,
            refresh.id,
            endpoint,
            {"fixture_scope": index},
            requested_at=now + timedelta(milliseconds=index),
        )
        for index, endpoint in enumerate(endpoints)
    )
    normalized_scope_manager.apply_scope(
        requests[0].id,
        LeagueEndpointRecords(
            league=LeagueRecord(
                sleeper_league_id=domain.sleeper_league_id,
                name="Projected League",
                status="in_season",
                season="2026",
                sport="nfl",
                scoring_settings={"passing_bonus": Decimal("1.125")},
                roster_positions=("QB", "RB"),
                provider_settings={"draft_rounds": 2},
                playoff_start_week=15,
                playoff_team_count=2,
                league_average_match=1,
            )
        ),
    )
    normalized_scope_manager.apply_scope(
        requests[1].id,
        LeagueUsersEndpointRecords(
            users=(
                UserRecord(
                    sleeper_user_id="u1",
                    display_name="Manager One",
                    metadata={"rank": 1},
                ),
                UserRecord(
                    sleeper_user_id="u2",
                    display_name="Manager Two",
                    metadata={"rank": 2},
                ),
            ),
            league_users=(
                LeagueUserRecord(
                    sleeper_user_id="u1",
                    team_name="Alpha Team",
                    is_commissioner=True,
                    metadata={},
                ),
                LeagueUserRecord(
                    sleeper_user_id="u2",
                    team_name="Beta Team",
                    metadata={},
                ),
            ),
        ),
    )
    normalized_scope_manager.apply_scope(
        requests[2].id,
        PlayerCatalogEndpointRecords(
            players=(
                PlayerRecord(
                    sleeper_player_id="p1",
                    full_name="Alpha Quarterback",
                    position="QB",
                    nfl_team="SEA",
                    active=True,
                    status="Active",
                    age=25,
                    years_experience=3,
                    metadata={"rating": Decimal("9.75")},
                ),
                PlayerRecord(
                    sleeper_player_id="p2",
                    full_name="Beta Runner",
                    position="RB",
                    nfl_team="SF",
                    active=True,
                    status="Active",
                    metadata={"rating": Decimal("8.5")},
                ),
                PlayerRecord(
                    sleeper_player_id="p3",
                    full_name="Beta Runner",
                    position="RB",
                    nfl_team="SEA",
                    active=False,
                    status="Inactive",
                    metadata={},
                ),
                PlayerRecord(
                    sleeper_player_id="p4",
                    full_name=None,
                    position="QB",
                    nfl_team="SEA",
                    active=True,
                    metadata={},
                ),
            )
        ),
    )
    normalized_scope_manager.apply_scope(
        requests[3].id,
        LeagueRostersEndpointRecords(
            rosters=(
                RosterRecord(
                    sleeper_roster_id="1",
                    settings={"waiver_position": 1},
                    metadata={"streak": "W2"},
                    record_string="2-0",
                    wins=2,
                    losses=0,
                    ties=0,
                    points_for=Decimal("200.75"),
                    points_against=Decimal("180.5"),
                ),
                RosterRecord(
                    sleeper_roster_id="2",
                    settings={"waiver_position": 2},
                    metadata={"streak": "L2"},
                    record_string="0-2",
                    wins=0,
                    losses=2,
                    ties=0,
                    points_for=Decimal("150.5"),
                    points_against=Decimal("190.25"),
                ),
            ),
            managers=(
                RosterManagerRecord(
                    sleeper_roster_id="1",
                    sleeper_user_id="u1",
                    role="owner",
                    source_order=0,
                ),
                RosterManagerRecord(
                    sleeper_roster_id="2",
                    sleeper_user_id="u2",
                    role="owner",
                    source_order=0,
                ),
            ),
            players=(
                RosterPlayerRecord(
                    sleeper_roster_id="1",
                    sleeper_player_id="p1",
                    role="starter",
                ),
                RosterPlayerRecord(
                    sleeper_roster_id="2",
                    sleeper_player_id="p2",
                    role="starter",
                ),
            ),
        ),
    )
    normalized_scope_manager.apply_scope(
        requests[4].id,
        MatchupsEndpointRecords(
            matchups=(
                MatchupRecord(
                    week=week,
                    sleeper_roster_id="1",
                    sleeper_matchup_id=1,
                    points=Decimal("101.5"),
                ),
                MatchupRecord(
                    week=week,
                    sleeper_roster_id="2",
                    sleeper_matchup_id=1,
                    points=Decimal("87.25"),
                ),
            ),
            player_performances=(
                PlayerPerformanceRecord(
                    week=week,
                    sleeper_roster_id="1",
                    sleeper_matchup_id=1,
                    sleeper_player_id="p1",
                    points=Decimal("25.125"),
                    role="starter",
                ),
            ),
        ),
    )
    normalized_scope_manager.apply_scope(
        requests[5].id,
        TransactionsEndpointRecords(
            transactions=(
                TransactionRecord(
                    week=week,
                    sleeper_transaction_id="tx1",
                    transaction_type="trade",
                    status="complete",
                    provider_created_at_ms=123456,
                    settings={"waiver_bid": Decimal("3.5")},
                    metadata={"note": "fixture"},
                ),
            ),
            moves=(
                TransactionMoveRecord(
                    sleeper_transaction_id="tx1",
                    move_index=0,
                    move_kind="player",
                    from_sleeper_roster_id="1",
                    to_sleeper_roster_id="2",
                    sleeper_player_id="p2",
                ),
            ),
        ),
    )
    refresh_manager.finish_refresh(refresh.id)
    return ProjectedSeason(
        domain=domain,
        refresh_run_id=refresh.id,
        league_request_id=requests[0].id,
        users_request_id=requests[1].id,
        player_request_id=requests[2].id,
        roster_request_id=requests[3].id,
        matchup_request_id=requests[4].id,
        transaction_request_id=requests[5].id,
        week=week,
        user_ids=("u1", "u2"),
        player_ids=("p1", "p2", "p3", "p4"),
        sleeper_transaction_id="tx1",
    )


@pytest.fixture
def managers(
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
) -> tuple[RefreshRunManager, ApiRequestManager]:
    return refresh_manager, request_manager
