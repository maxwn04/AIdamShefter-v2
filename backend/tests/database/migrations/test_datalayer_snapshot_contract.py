from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text

from backend.database.models.core import Competition, CompetitionSeason


def _config(database_url: str, *, output_buffer: StringIO | None = None) -> Config:
    root = Path(__file__).resolve().parents[4]
    config = Config(
        str(root / "backend" / "migrations" / "alembic.ini"),
        output_buffer=output_buffer,
    )
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def test_snapshot_contract_upgrade_and_downgrade_compile_offline() -> None:
    upgrade_sql = StringIO()
    command.upgrade(
        _config("postgresql+psycopg://unused:unused@localhost/unused", output_buffer=upgrade_sql),
        "0007",
        sql=True,
    )
    upgrade = upgrade_sql.getvalue()
    assert "ADD COLUMN build_key" in upgrade
    assert "ADD COLUMN as_of_date DATE" in upgrade
    assert "uq_data_snapshots_active_build_key" in upgrade
    assert "fk_data_snapshot_requests_request_scope_hash" in upgrade

    downgrade_sql = StringIO()
    command.downgrade(
        _config(
            "postgresql+psycopg://unused:unused@localhost/unused",
            output_buffer=downgrade_sql,
        ),
        "0007:0006",
        sql=True,
    )
    downgrade = downgrade_sql.getvalue()
    assert "DROP COLUMN build_key" in downgrade
    assert "ADD COLUMN mode TEXT" in downgrade
    assert "fk_data_snapshot_requests_request_scope" in downgrade


def test_snapshot_contract_migrates_legacy_rows_and_reverses(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIDAM_MIGRATION_REQUIRE_TLS", "false")
    monkeypatch.setenv("AIDAM_MIGRATION_ROLE", "aidam_owner")
    config = _config(database_url)
    command.upgrade(config, "0006")

    competition_id = uuid4()
    season_id = uuid4()
    snapshot_id = uuid4()
    legacy_cutoff = datetime(2026, 10, 27, 23, 45, tzinfo=timezone.utc)
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            {"id": competition_id, "display_name": "Migration Test League"},
        )
        connection.execute(
            sa.insert(CompetitionSeason),
            {
                "id": season_id,
                "competition_id": competition_id,
                "season_year": 2026,
                "sequence_number": 1,
                "sleeper_league_id": f"league-{uuid4()}",
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO sleeper.data_snapshots (
                    id, competition_id, primary_competition_season_id, mode,
                    domain_cutoff_week, knowledge_cutoff_at, status,
                    materializer_version, sqlite_schema_version, code_version,
                    completeness_warnings
                ) VALUES (
                    :id, :competition_id, :season_id, 'historical', 8,
                    :knowledge_cutoff_at, 'building', 'projection-v1',
                    'sqlite-v1', 'code-v1', '[]'::jsonb
                )
                """
            ),
            {
                "id": snapshot_id,
                "competition_id": competition_id,
                "season_id": season_id,
                "knowledge_cutoff_at": legacy_cutoff,
            },
        )

    command.upgrade(config, "0007")
    with engine.connect() as connection:
        columns = {
            column["name"]
            for column in inspect(connection).get_columns(
                "data_snapshots", schema="sleeper"
            )
        }
        row = connection.execute(
            text(
                """
                SELECT build_key, as_of_date, snapshot_projection_version,
                       failure_summary
                FROM sleeper.data_snapshots
                WHERE id = :snapshot_id
                """
            ),
            {"snapshot_id": snapshot_id},
        ).one()
    assert {
        "build_key",
        "as_of_date",
        "snapshot_projection_version",
        "failure_summary",
    } <= columns
    assert {
        "mode",
        "knowledge_cutoff_at",
        "materializer_version",
        "sqlite_schema_version",
        "selected_request_set_sha256",
    }.isdisjoint(columns)
    assert row.build_key == f"legacy:{snapshot_id}"
    assert row.as_of_date == date(2026, 10, 27)
    assert row.snapshot_projection_version == "projection-v1"
    assert row.failure_summary is None

    command.downgrade(config, "0006")
    with engine.connect() as connection:
        columns = {
            column["name"]
            for column in inspect(connection).get_columns(
                "data_snapshots", schema="sleeper"
            )
        }
        row = connection.execute(
            text(
                """
                SELECT mode, knowledge_cutoff_at, materializer_version,
                       sqlite_schema_version, selected_request_set_sha256
                FROM sleeper.data_snapshots
                WHERE id = :snapshot_id
                """
            ),
            {"snapshot_id": snapshot_id},
        ).one()
    assert {
        "mode",
        "knowledge_cutoff_at",
        "materializer_version",
        "sqlite_schema_version",
        "selected_request_set_sha256",
    } <= columns
    assert row.mode == "legacy"
    assert row.knowledge_cutoff_at == datetime(2026, 10, 27, tzinfo=timezone.utc)
    assert row.materializer_version == "projection-v1"
    assert row.sqlite_schema_version == "projection-v1"
    assert row.selected_request_set_sha256 is None

    command.upgrade(config, "0007")
    command.downgrade(config, "base")
    engine.dispose()
