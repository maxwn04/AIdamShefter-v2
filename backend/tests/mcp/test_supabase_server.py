from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from mcp import Client

from mcp_servers import supabase


@pytest.mark.asyncio
async def test_mcp_exposes_expected_tools() -> None:
    async with Client(supabase.mcp) as client:
        result = await client.list_tools()

    assert {tool.name for tool in result.tools} == {
        "check_database_connection",
        "execute_sql",
        "list_database_objects",
    }


def test_psycopg_connection_url_accepts_project_driver() -> None:
    result = supabase._psycopg_connection_url(
        "postgresql+psycopg://user:p%40ss@database.example/aidam?sslmode=require"
    )

    assert result == (
        "postgresql://user:p%40ss@database.example/aidam?sslmode=require"
    )


def test_psycopg_connection_url_rejects_non_postgres() -> None:
    with pytest.raises(ValueError, match="must use PostgreSQL"):
        supabase._psycopg_connection_url("sqlite:///local.sqlite")


def test_configured_database_url_prefers_explicit_supabase_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(supabase, "load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setenv("AIDAM_MIGRATION_DATABASE_URL", "postgresql://fallback")
    monkeypatch.setenv("SUPABASE_DATABASE_URL", "postgresql://preferred")

    assert supabase._configured_database_url() == (
        "postgresql://preferred",
        "SUPABASE_DATABASE_URL",
    )


def test_configured_database_url_loads_configured_env_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = supabase.PROJECT_ROOT / "server.env"
    loaded_files: list[Path] = []

    def fake_load_dotenv(path: Path, *, override: bool) -> bool:
        loaded_files.append(path)
        monkeypatch.setenv(
            "AIDAM_MIGRATION_DATABASE_URL", "postgresql://from-file"
        )
        return True

    monkeypatch.setattr(supabase, "load_dotenv", fake_load_dotenv)
    monkeypatch.setenv(supabase.MCP_ENV_FILE_ENVIRONMENT, str(env_file))
    for environment_name in supabase.DATABASE_URL_ENVIRONMENTS:
        monkeypatch.delenv(environment_name, raising=False)

    assert supabase._configured_database_url() == (
        "postgresql://from-file",
        "AIDAM_MIGRATION_DATABASE_URL",
    )
    assert loaded_files == [env_file]


def test_configured_database_url_requires_a_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(supabase, "load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.delenv(supabase.MCP_ENV_FILE_ENVIRONMENT, raising=False)
    for environment_name in supabase.DATABASE_URL_ENVIRONMENTS:
        monkeypatch.delenv(environment_name, raising=False)

    with pytest.raises(RuntimeError, match="Database connection is not configured"):
        supabase._configured_database_url()


def test_json_safe_normalizes_database_values() -> None:
    result = supabase._json_safe(
        {
            "created_at": datetime(2026, 8, 29, tzinfo=timezone.utc),
            "score": Decimal("123.45"),
            "payload": b"hello",
        }
    )

    assert result == {
        "created_at": "2026-08-29 00:00:00+00:00",
        "score": "123.45",
        "payload": "aGVsbG8=",
    }


def test_execute_sql_validates_limits_before_connecting() -> None:
    with pytest.raises(ValueError, match="statement must not be empty"):
        supabase.execute_sql("   ")
    with pytest.raises(ValueError, match="max_rows must be between"):
        supabase.execute_sql("SELECT 1", max_rows=0)
