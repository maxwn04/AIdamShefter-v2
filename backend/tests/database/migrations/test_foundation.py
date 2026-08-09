from pathlib import Path
from typing import cast

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text

from backend.database.base import APPLICATION_SCHEMAS


def _config(database_url: str) -> Config:
    root = Path(__file__).resolve().parents[4]
    config = Config(str(root / "backend" / "migrations" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def test_foundation_upgrade_downgrade_and_reupgrade(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIDAM_MIGRATION_REQUIRE_TLS", "false")
    monkeypatch.setenv("AIDAM_MIGRATION_ROLE", "aidam_owner")
    config = _config(database_url)

    command.upgrade(config, "0001")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        schemas = set(inspect(connection).get_schema_names())
        assert set(APPLICATION_SCHEMAS) <= schemas
        assert connection.execute(
            text("SELECT version_num FROM public.alembic_version")
        ).scalar_one() == "0001"
        public_create = cast(
            bool,
            connection.execute(
                text("SELECT has_schema_privilege('public', 'public', 'CREATE')")
            ).scalar_one(),
        )
        assert public_create is False

    command.downgrade(config, "base")
    with engine.connect() as connection:
        schemas = set(inspect(connection).get_schema_names())
        assert not set(APPLICATION_SCHEMAS) & schemas

    command.upgrade(config, "0001")
    command.downgrade(config, "base")
    engine.dispose()
