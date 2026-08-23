"""Disposable PostgreSQL fixtures for artifact resource tests."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from backend.database.sessions import SessionFactory, create_session_factory
from backend.resources.reporting.artifacts import ArtifactManager
from backend.tests.database.conftest import database_engine, migrated_database
from backend.tests.resources.reporting.generations.conftest import (
    GenerationDomain,
    generation_context,
    seed_generation_domain,
)


@pytest.fixture(autouse=True)
def clean_artifact_resources(request: pytest.FixtureRequest) -> None:
    if "database_engine" not in request.fixturenames:
        return
    engine = request.getfixturevalue("database_engine")
    with engine.begin() as connection:
        connection.execute(sa.text("TRUNCATE TABLE core.competitions CASCADE"))


@pytest.fixture
def generation_domain(database_engine) -> GenerationDomain:
    return seed_generation_domain(database_engine, label="Artifact Resource")


@pytest.fixture
def session_factory(database_engine) -> SessionFactory:
    return create_session_factory(database_engine)


@pytest.fixture
def artifact_manager(
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> ArtifactManager:
    return ArtifactManager(session_factory, generation_context(generation_domain))


__all__ = ["database_engine", "migrated_database"]
