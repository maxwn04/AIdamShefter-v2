"""Reusable PostgreSQL fixtures for Sleeper resource-manager tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
from backend.services.datalayer.sleeper.endpoints.contracts import CompletenessFinding
from backend.tests.database.conftest import database_engine, migrated_database


@pytest.fixture(autouse=True)
def clean_sleeper_resources(request: pytest.FixtureRequest) -> None:
    """Start every Sleeper resource test with no aggregate or domain rows."""

    if "database_engine" not in request.fixturenames:
        return
    database_engine = request.getfixturevalue("database_engine")
    with database_engine.begin() as connection:
        connection.execute(
            sa.text("TRUNCATE TABLE core.competitions, " "sleeper.api_payloads CASCADE")
        )


@dataclass(frozen=True)
class Domain:
    competition_id: UUID
    season_id: UUID
    sleeper_league_id: str
    franchise_ids: tuple[UUID, UUID]
    roster_ids: tuple[UUID, UUID]


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
def managers(
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
) -> tuple[RefreshRunManager, ApiRequestManager]:
    return refresh_manager, request_manager
