"""Isolated PostgreSQL databases for migration and constraint tests."""

from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path
import re
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

_DATABASE_NAME = re.compile(r"^aidam_test_[a-f0-9]{16}$")


def _alembic_config(database_url: str) -> Config:
    root = Path(__file__).resolve().parents[3]
    config = Config(str(root / "backend" / "migrations" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def _test_database_base_url() -> str:
    base_url = os.getenv("AIDAM_TEST_DATABASE_URL")
    if not base_url:
        pytest.skip("AIDAM_TEST_DATABASE_URL is required for PostgreSQL tests")
    parsed = make_url(base_url)
    if parsed.drivername != "postgresql+psycopg":
        raise ValueError("AIDAM_TEST_DATABASE_URL must use postgresql+psycopg")
    return base_url


@contextmanager
def _temporary_database(base_url: str) -> Iterator[str]:
    parsed = make_url(base_url)
    database_name = f"aidam_test_{uuid4().hex[:16]}"
    if not _DATABASE_NAME.fullmatch(database_name):
        raise RuntimeError("refusing to create an unexpected test database name")

    admin_url = parsed.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        _ = connection.exec_driver_sql(
            f'CREATE DATABASE "{database_name}" OWNER aidam_owner'
        )
    bootstrap_engine = create_engine(
        parsed.set(database=database_name),
        isolation_level="AUTOCOMMIT",
    )
    with bootstrap_engine.connect() as connection:
        _ = connection.exec_driver_sql(
            "REVOKE CREATE ON SCHEMA public FROM PUBLIC"
        )
    bootstrap_engine.dispose()
    test_url = parsed.set(database=database_name).render_as_string(
        hide_password=False
    )

    try:
        yield test_url
    finally:
        with admin_engine.connect() as connection:
            _ = connection.execute(
                text(
                    """
                    SELECT pg_catalog.pg_terminate_backend(pid)
                    FROM pg_catalog.pg_stat_activity
                    WHERE datname = :database_name
                      AND pid <> pg_catalog.pg_backend_pid()
                    """
                ),
                {"database_name": database_name},
            )
            _ = connection.exec_driver_sql(f'DROP DATABASE "{database_name}"')
        admin_engine.dispose()


@pytest.fixture
def database_url() -> Iterator[str]:
    """Create a unique empty database for one migration test."""

    with _temporary_database(_test_database_base_url()) as test_url:
        yield test_url


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[str]:
    """Upgrade an isolated database to the current single Alembic head."""

    with _temporary_database(_test_database_base_url()) as test_url:
        old_tls = os.environ.get("AIDAM_MIGRATION_REQUIRE_TLS")
        old_role = os.environ.get("AIDAM_MIGRATION_ROLE")
        os.environ["AIDAM_MIGRATION_REQUIRE_TLS"] = "false"
        os.environ["AIDAM_MIGRATION_ROLE"] = "aidam_owner"
        config = _alembic_config(test_url)
        command.upgrade(config, "head")
        try:
            yield test_url
        finally:
            command.downgrade(config, "base")
            if old_tls is None:
                _ = os.environ.pop("AIDAM_MIGRATION_REQUIRE_TLS", None)
            else:
                os.environ["AIDAM_MIGRATION_REQUIRE_TLS"] = old_tls
            if old_role is None:
                _ = os.environ.pop("AIDAM_MIGRATION_ROLE", None)
            else:
                os.environ["AIDAM_MIGRATION_ROLE"] = old_role


@pytest.fixture(scope="session")
def database_engine(migrated_database: str) -> Iterator[Engine]:
    """Connect to the fully migrated isolated database."""

    engine = create_engine(migrated_database, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()
