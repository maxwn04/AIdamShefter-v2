"""Disposable PostgreSQL fixtures for generation memory-recall tests."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from backend.database.sessions import SessionFactory, create_session_factory
from backend.resources.reporting.memory_recalls import GenerationMemoryRecallManager
from backend.tests.database.conftest import database_engine, migrated_database
from backend.tests.resources.reporting.generations.conftest import (
    GenerationDomain,
    generation_context,
    seed_generation_domain,
)


@pytest.fixture(autouse=True)
def clean_memory_recall_resources(request: pytest.FixtureRequest) -> None:
    if "database_engine" not in request.fixturenames:
        return
    engine = request.getfixturevalue("database_engine")
    with engine.begin() as connection:
        connection.execute(sa.text("TRUNCATE TABLE core.competitions CASCADE"))


@pytest.fixture
def generation_domain(database_engine) -> GenerationDomain:
    return seed_generation_domain(database_engine, label="Memory Recall Resource")


@pytest.fixture
def session_factory(database_engine) -> SessionFactory:
    return create_session_factory(database_engine)


@pytest.fixture
def memory_recall_manager(
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> GenerationMemoryRecallManager:
    return GenerationMemoryRecallManager(
        session_factory,
        generation_context(generation_domain),
    )


__all__ = ["database_engine", "migrated_database"]
