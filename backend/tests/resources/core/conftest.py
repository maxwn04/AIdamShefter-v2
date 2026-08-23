from __future__ import annotations

from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.sessions import SessionFactory, create_session_factory
from backend.resources.context import (
    CompetitionScope,
    GlobalScope,
    LocalUserActor,
    ManagerContext,
)
from backend.resources.core import CompetitionManager
from backend.tests.database.conftest import database_engine, migrated_database


@pytest.fixture(autouse=True)
def clean_core_resources(request: pytest.FixtureRequest) -> None:
    if "database_engine" not in request.fixturenames:
        return
    engine = request.getfixturevalue("database_engine")
    with engine.begin() as connection:
        connection.execute(sa.text("TRUNCATE TABLE core.competitions CASCADE"))


@pytest.fixture
def session_factory(database_engine: Engine) -> SessionFactory:
    return create_session_factory(database_engine)


def global_context() -> ManagerContext[GlobalScope]:
    return ManagerContext[GlobalScope](
        actor=LocalUserActor(),
        scope=GlobalScope(reason="manage competition catalog"),
        correlation_id=uuid4(),
    )


def competition_context(
    competition_id: UUID,
) -> ManagerContext[CompetitionScope]:
    return ManagerContext[CompetitionScope](
        actor=LocalUserActor(),
        scope=CompetitionScope(competition_id=competition_id),
        correlation_id=uuid4(),
    )


@pytest.fixture
def competition_manager(session_factory: SessionFactory) -> CompetitionManager:
    return CompetitionManager(session_factory, global_context())


__all__ = ["database_engine", "migrated_database"]
