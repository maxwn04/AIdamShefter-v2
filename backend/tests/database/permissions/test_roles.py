from typing import cast

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from backend.database.base import APPLICATION_SCHEMAS
from backend.database.health import read_database_health


@pytest.mark.parametrize("role", ["aidam_api", "aidam_worker"])
def test_runtime_roles_can_use_but_not_create_in_application_schemas(
    database_engine: Engine,
    role: str,
) -> None:
    with database_engine.begin() as connection:
        _ = connection.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
        for schema in APPLICATION_SCHEMAS:
            can_use = cast(
                bool,
                connection.execute(
                    text("SELECT has_schema_privilege(:schema, 'USAGE')"),
                    {"schema": schema},
                ).scalar_one(),
            )
            can_create = cast(
                bool,
                connection.execute(
                    text("SELECT has_schema_privilege(:schema, 'CREATE')"),
                    {"schema": schema},
                ).scalar_one(),
            )
            assert can_use is True
            assert can_create is False


@pytest.mark.parametrize("role", ["aidam_api", "aidam_worker"])
def test_runtime_roles_cannot_execute_ddl(
    database_engine: Engine,
    role: str,
) -> None:
    with database_engine.connect() as connection:
        transaction = connection.begin()
        _ = connection.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
        with pytest.raises(ProgrammingError):
            _ = connection.execute(
                text("CREATE TABLE core.forbidden (id integer)")
            )
        transaction.rollback()


@pytest.mark.parametrize("role", ["aidam_api", "aidam_worker"])
def test_runtime_roles_cannot_read_migration_history(
    database_engine: Engine,
    role: str,
) -> None:
    with database_engine.begin() as connection:
        _ = connection.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
        can_read = cast(
            bool,
            connection.execute(
                text(
                    "SELECT has_table_privilege('public.alembic_version', 'SELECT')"
                )
            ).scalar_one(),
        )

    assert can_read is False


@pytest.mark.parametrize(
    ("role", "password"),
    [
        ("aidam_api", "aidam_local_api"),
        ("aidam_worker", "aidam_local_worker"),
    ],
)
def test_runtime_health_succeeds_without_migration_history_access(
    migrated_database: str,
    role: str,
    password: str,
) -> None:
    runtime_url = make_url(migrated_database).set(
        username=role,
        password=password,
    )
    engine = create_engine(runtime_url)
    try:
        health = read_database_health(engine)
    finally:
        engine.dispose()

    assert health.database == make_url(migrated_database).database
    assert health.role == role
    assert health.alembic_revision is None
