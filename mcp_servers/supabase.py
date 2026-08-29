"""Local stdio MCP server with direct, unrestricted Supabase PostgreSQL access."""

from __future__ import annotations

import base64
import json
import os
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any, TypeAlias
from uuid import UUID

import psycopg
from dotenv import load_dotenv
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ENV_FILE = PROJECT_ROOT / ".env"
MCP_ENV_FILE_ENVIRONMENT = "AIDAM_MCP_ENV_FILE"
DATABASE_URL_ENVIRONMENTS = (
    "SUPABASE_DATABASE_URL",
    "AIDAM_MIGRATION_DATABASE_URL",
)
MAX_RETURNED_ROWS = 10_000

JsonScalar: TypeAlias = str | int | float | bool | None
SqlParameters: TypeAlias = dict[str, JsonScalar] | list[JsonScalar] | None

mcp = MCPServer(
    "AIdam Supabase",
    version="0.1.0",
    instructions=(
        "Direct PostgreSQL access to the configured Supabase database. "
        "The execute_sql tool is unrestricted and can read, modify, or delete data "
        "and database objects. Inspect the target and use transactions when a change "
        "needs to be atomic."
    ),
)


def _configured_database_url() -> tuple[str, str]:
    configured_env_file = os.getenv(MCP_ENV_FILE_ENVIRONMENT)
    env_file = Path(configured_env_file) if configured_env_file else PROJECT_ENV_FILE
    load_dotenv(env_file, override=False)
    for environment_name in DATABASE_URL_ENVIRONMENTS:
        value = os.getenv(environment_name)
        if value:
            return value, environment_name
    expected = " or ".join(DATABASE_URL_ENVIRONMENTS)
    raise RuntimeError(
        f"Database connection is not configured. Set {expected} in "
        f"{env_file} or in the MCP server process environment."
    )


def _psycopg_connection_url(database_url: str) -> str:
    """Convert the project's SQLAlchemy URL spelling to a libpq URL."""
    url = make_url(database_url)
    if url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise ValueError("database URL must use PostgreSQL with the psycopg driver")
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def _connect() -> psycopg.Connection[dict[str, Any]]:
    database_url, _ = _configured_database_url()
    return psycopg.connect(
        _psycopg_connection_url(database_url),
        autocommit=True,
        connect_timeout=10,
        application_name="aidam-supabase-mcp",
        row_factory=dict_row,
    )


def _json_default(value: Any) -> JsonScalar:
    if isinstance(value, (datetime, date, time, Decimal, UUID)):
        return str(value)
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    return str(value)


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_json_default))


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )
)
def check_database_connection() -> dict[str, Any]:
    """Test the database connection and return its non-secret identity."""
    _, environment_name = _configured_database_url()
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT
                current_database() AS database,
                current_user AS database_user,
                inet_server_addr()::text AS server_address,
                current_setting('server_version') AS server_version
            """
        ).fetchone()
    return {
        "connected": True,
        "credential_source": environment_name,
        **_json_safe(row),
    }


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )
)
def list_database_objects(
    schema: str | None = None,
) -> dict[str, Any]:
    """List user-visible tables and views, optionally within one schema."""
    query = """
        SELECT
            table_schema AS schema,
            table_name AS name,
            table_type AS type
        FROM information_schema.tables
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
          AND (%(schema)s IS NULL OR table_schema = %(schema)s)
        ORDER BY table_schema, table_name
    """
    with _connect() as connection:
        rows = connection.execute(query, {"schema": schema}).fetchall()
    return {"objects": _json_safe(rows), "count": len(rows)}


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=True,
    )
)
def execute_sql(
    statement: str,
    parameters: SqlParameters = None,
    max_rows: int = 1_000,
) -> dict[str, Any]:
    """Execute unrestricted PostgreSQL SQL, including reads, writes, and DDL.

    Use psycopg placeholders: ``%(name)s`` with an object of named parameters,
    or ``%s`` with an array of positional parameters. Multiple SQL statements
    are allowed when PostgreSQL accepts them. ``max_rows`` limits only rows
    returned to the MCP client; it does not limit affected rows.
    """
    if not statement.strip():
        raise ValueError("statement must not be empty")
    if not 1 <= max_rows <= MAX_RETURNED_ROWS:
        raise ValueError(f"max_rows must be between 1 and {MAX_RETURNED_ROWS}")

    started_at = perf_counter()
    result_sets: list[dict[str, Any]] = []
    bound_parameters: Any = parameters
    if isinstance(parameters, list):
        bound_parameters = tuple(parameters)

    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(statement, bound_parameters, prepare=False)
            while True:
                status = cursor.statusmessage or ""
                if cursor.description is None:
                    result_sets.append(
                        {
                            "status": status,
                            "affected_rows": max(cursor.rowcount, 0),
                        }
                    )
                else:
                    rows = cursor.fetchmany(max_rows + 1)
                    truncated = len(rows) > max_rows
                    visible_rows = rows[:max_rows]
                    result_sets.append(
                        {
                            "status": status,
                            "columns": [column.name for column in cursor.description],
                            "rows": _json_safe(visible_rows),
                            "returned_rows": len(visible_rows),
                            "truncated": truncated,
                        }
                    )
                if cursor.nextset() is None:
                    break

    return {
        "result_sets": result_sets,
        "elapsed_ms": round((perf_counter() - started_at) * 1_000, 2),
    }


def main() -> None:
    """Run the local server over standard input/output."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
