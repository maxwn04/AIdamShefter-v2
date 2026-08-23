"""Disposable PostgreSQL fixtures for generation lifecycle tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.core import Competition, CompetitionSeason
from backend.database.models.memory import MemoryRevision
from backend.database.models.sleeper import DataSnapshot
from backend.database.sessions import SessionFactory, create_session_factory
from backend.resources.context import (
    CompetitionScope,
    ManagerContext,
    SystemProcessActor,
)
from backend.resources.reporting.generations import GenerationManager
from backend.tests.database.conftest import database_engine, migrated_database


@dataclass(frozen=True)
class GenerationDomain:
    competition_id: UUID
    season_id: UUID
    memory_revision_id: UUID
    snapshot_id: UUID


@pytest.fixture(autouse=True)
def clean_generation_resources(request: pytest.FixtureRequest) -> None:
    if "database_engine" not in request.fixturenames:
        return
    engine = request.getfixturevalue("database_engine")
    with engine.begin() as connection:
        connection.execute(sa.text("TRUNCATE TABLE core.competitions CASCADE"))


def seed_generation_domain(
    database_engine: Engine,
    *,
    label: str = "Generation Resource",
    snapshot_status: str = "ready",
) -> GenerationDomain:
    competition_id = uuid4()
    season_id = uuid4()
    memory_revision_id = uuid4()
    snapshot_id = uuid4()
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            {"id": competition_id, "display_name": label},
        )
        connection.execute(
            sa.insert(CompetitionSeason),
            {
                "id": season_id,
                "competition_id": competition_id,
                "season_year": 2026,
                "sequence_number": 1,
                "sleeper_league_id": f"league-{uuid4()}",
            },
        )
        connection.execute(
            sa.insert(MemoryRevision),
            {
                "id": memory_revision_id,
                "competition_id": competition_id,
                "sequence_number": 0,
                "competition_season_id": season_id,
                "state_content_hash": "root-state",
            },
        )
        connection.execute(
            sa.insert(DataSnapshot),
            {
                "id": snapshot_id,
                "competition_id": competition_id,
                "primary_competition_season_id": season_id,
                "build_key": uuid4().hex + uuid4().hex,
                "domain_cutoff_week": 8,
                "domain_cutoff_at": None,
                "as_of_date": date(2026, 10, 27),
                "status": snapshot_status,
                "snapshot_projection_version": "1",
                "code_version": "test",
                "completeness_warnings": [],
                "sqlite_artifact_sha256": "a" * 64,
                "sqlite_artifact_byte_length": 10,
                "sqlite_artifact_storage_key": "snapshots/test.sqlite",
            },
        )
    return GenerationDomain(
        competition_id=competition_id,
        season_id=season_id,
        memory_revision_id=memory_revision_id,
        snapshot_id=snapshot_id,
    )


def generation_context(domain: GenerationDomain) -> ManagerContext[CompetitionScope]:
    return ManagerContext[CompetitionScope](
        actor=SystemProcessActor(process_name="generation-test"),
        scope=CompetitionScope(competition_id=domain.competition_id),
        correlation_id=uuid4(),
    )


@pytest.fixture
def generation_domain(database_engine: Engine) -> GenerationDomain:
    return seed_generation_domain(database_engine)


@pytest.fixture
def session_factory(database_engine: Engine) -> SessionFactory:
    return create_session_factory(database_engine)


@pytest.fixture
def generation_manager(
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> GenerationManager:
    return GenerationManager(session_factory, generation_context(generation_domain))
