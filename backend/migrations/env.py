"""Alembic environment for AIdam's single schema-qualified history."""

from __future__ import annotations

from logging.config import fileConfig
import os
import re

from alembic import context
from sqlalchemy import Connection, create_engine, pool, text

from backend.database.base import APPLICATION_SCHEMAS
from backend.database.registry import metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata
_MIGRATION_LOCK_ID = 280_486_483_277
_ROLE_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")


def _database_url() -> str:
    url = os.getenv("AIDAM_MIGRATION_DATABASE_URL")
    if url:
        return url
    configured = config.get_main_option("sqlalchemy.url")
    if "URL_MUST_BE_SUPPLIED" in configured:
        raise RuntimeError("AIDAM_MIGRATION_DATABASE_URL is required")
    return configured


def _include_name(
    name: str | None,
    type_: str,
    parent_names: dict[str, str | None],
) -> bool:
    if type_ == "schema":
        return name in APPLICATION_SCHEMAS
    schema_name = parent_names.get("schema_name")
    return schema_name is None or schema_name in APPLICATION_SCHEMAS


def _configure(connection: Connection | None = None, *, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=_include_name,
        compare_type=True,
        compare_server_default=True,
        version_table="alembic_version",
        version_table_schema="public",
        transactional_ddl=True,
        literal_binds=connection is None,
        dialect_opts={"paramstyle": "named"} if connection is None else None,
    )


def run_migrations_offline() -> None:
    _configure(url=_database_url())
    with context.begin_transaction():
        context.run_migrations()


def _run_with_connection(connection: Connection) -> None:
    role = os.getenv("AIDAM_MIGRATION_ROLE", "aidam_owner")
    if role and not _ROLE_PATTERN.fullmatch(role):
        raise RuntimeError("AIDAM_MIGRATION_ROLE is not a valid PostgreSQL identifier")

    with connection.begin():
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text("SET LOCAL search_path = pg_catalog"))
        if role:
            connection.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
        connection.execute(
            text("SELECT pg_catalog.pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _MIGRATION_LOCK_ID},
        )
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_online() -> None:
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        _run_with_connection(supplied_connection)
        return

    connect_args: dict[str, str | int] = {
        "application_name": "aidam-alembic",
        "connect_timeout": 10,
    }
    require_tls = os.getenv("AIDAM_MIGRATION_REQUIRE_TLS", "true").lower() not in {
        "0",
        "false",
        "no",
    }
    if require_tls:
        ca_file = os.getenv("AIDAM_DATABASE_CA_FILE")
        if not ca_file:
            raise RuntimeError(
                "AIDAM_DATABASE_CA_FILE is required for verified migration TLS"
            )
        connect_args.update(sslmode="verify-full", sslrootcert=ca_file)
    else:
        connect_args["sslmode"] = "disable"

    engine = create_engine(
        _database_url(),
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )
    with engine.connect() as connection:
        _run_with_connection(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
