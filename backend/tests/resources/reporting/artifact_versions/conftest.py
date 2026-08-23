"""Disposable PostgreSQL fixtures for artifact-version resource tests."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from backend.database.sessions import SessionFactory, create_session_factory
from backend.resources.reporting.artifact_versions import ArtifactVersionManager
from backend.tests.database.conftest import database_engine, migrated_database
from backend.tests.resources.reporting.generations.conftest import (
    GenerationDomain,
    generation_context,
    seed_generation_domain,
)


@pytest.fixture(autouse=True)
def clean_artifact_version_resources(request: pytest.FixtureRequest) -> None:
    if "database_engine" not in request.fixturenames:
        return
    engine = request.getfixturevalue("database_engine")
    with engine.begin() as connection:
        connection.execute(sa.text("TRUNCATE TABLE core.competitions CASCADE"))


@pytest.fixture
def generation_domain(database_engine) -> GenerationDomain:
    return seed_generation_domain(database_engine, label="Artifact Version Resource")


@pytest.fixture
def session_factory(database_engine) -> SessionFactory:
    return create_session_factory(database_engine)


@pytest.fixture
def artifact_version_manager(
    session_factory: SessionFactory,
    generation_domain: GenerationDomain,
) -> ArtifactVersionManager:
    return ArtifactVersionManager(
        session_factory, generation_context(generation_domain)
    )


__all__ = ["database_engine", "migrated_database"]
