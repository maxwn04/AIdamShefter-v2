"""Bounded database readiness and identity checks."""

from dataclasses import dataclass
from typing import cast

from sqlalchemy import Engine, text


@dataclass(frozen=True, slots=True)
class DatabaseHealth:
    database: str
    role: str
    server_version: str
    tls: bool
    alembic_revision: str | None


def read_database_health(
    engine: Engine,
    *,
    include_migration_revision: bool = False,
) -> DatabaseHealth:
    """Read non-secret identity, optionally including protected migration state.

    Runtime roles intentionally cannot read ``public.alembic_version``. API and
    worker readiness therefore use the safe default, while migrator/operator
    checks opt in to revision verification.
    """

    with engine.connect() as connection:
        identity = connection.execute(
            text(
                """
                SELECT
                    current_database() AS database,
                    current_user AS role,
                    current_setting('server_version') AS server_version,
                    EXISTS (
                        SELECT 1
                        FROM pg_catalog.pg_stat_ssl
                        WHERE pid = pg_catalog.pg_backend_pid() AND ssl
                    ) AS tls
                """
            )
        ).mappings().one()
        revision = None
        if include_migration_revision:
            has_migration_table = cast(
                bool,
                connection.execute(
                    text(
                        """
                        SELECT pg_catalog.to_regclass(
                            'public.alembic_version'
                        ) IS NOT NULL
                        """
                    )
                ).scalar_one(),
            )
            if has_migration_table:
                revision = cast(
                    str | None,
                    connection.execute(
                        text("SELECT version_num FROM public.alembic_version")
                    ).scalar_one_or_none(),
                )

    return DatabaseHealth(
        database=cast(str, identity["database"]),
        role=cast(str, identity["role"]),
        server_version=cast(str, identity["server_version"]),
        tls=cast(bool, identity["tls"]),
        alembic_revision=revision,
    )


def assert_database_ready(
    health: DatabaseHealth,
    *,
    expected_database: str | None = None,
    expected_role: str | None = None,
    expected_revision: str | None = None,
    require_tls: bool = True,
) -> None:
    """Raise when the requested readiness invariants do not match intent.

    Runtime callers omit ``expected_revision`` because their least-privilege
    roles cannot inspect migration history. Deployment/operator readiness passes
    an expected revision after opting into it with ``read_database_health``.
    """

    mismatches: list[str] = []
    if expected_database is not None and health.database != expected_database:
        mismatches.append("database identity")
    if expected_role is not None and health.role != expected_role:
        mismatches.append("database role")
    if expected_revision is not None and health.alembic_revision != expected_revision:
        mismatches.append("Alembic revision")
    if require_tls and not health.tls:
        mismatches.append("TLS")
    if mismatches:
        raise RuntimeError(f"database readiness check failed: {', '.join(mismatches)}")
