from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy import Connection

from backend.database.health import (
    DatabaseHealth,
    _client_connection_uses_tls,
    assert_database_ready,
)


def test_client_tls_signal_supports_connection_poolers() -> None:
    connection = cast(
        Connection,
        SimpleNamespace(
            connection=SimpleNamespace(
                driver_connection=SimpleNamespace(
                    pgconn=SimpleNamespace(ssl_in_use=True)
                )
            )
        ),
    )

    assert _client_connection_uses_tls(connection) is True


def test_readiness_accepts_matching_identity() -> None:
    health = DatabaseHealth(
        database="aidam",
        role="aidam_api",
        server_version="17.4",
        tls=True,
        alembic_revision="0001",
    )

    assert_database_ready(
        health,
        expected_database="aidam",
        expected_role="aidam_api",
        expected_revision="0001",
    )


def test_runtime_readiness_does_not_require_migration_revision() -> None:
    health = DatabaseHealth(
        database="aidam",
        role="aidam_api",
        server_version="17.4",
        tls=True,
        alembic_revision=None,
    )

    assert_database_ready(
        health,
        expected_database="aidam",
        expected_role="aidam_api",
    )


def test_operator_readiness_fails_when_revision_was_not_loaded() -> None:
    health = DatabaseHealth(
        database="aidam",
        role="aidam_migrator",
        server_version="17.4",
        tls=True,
        alembic_revision=None,
    )

    with pytest.raises(RuntimeError, match="Alembic revision"):
        assert_database_ready(health, expected_revision="0006")


def test_readiness_reports_only_safe_mismatch_categories() -> None:
    health = DatabaseHealth(
        database="wrong",
        role="wrong",
        server_version="17.4",
        tls=False,
        alembic_revision=None,
    )

    with pytest.raises(RuntimeError) as raised:
        assert_database_ready(
            health,
            expected_database="aidam",
            expected_role="aidam_api",
            expected_revision="0001",
        )

    assert str(raised.value) == (
        "database readiness check failed: database identity, database role, "
        "Alembic revision, TLS"
    )
