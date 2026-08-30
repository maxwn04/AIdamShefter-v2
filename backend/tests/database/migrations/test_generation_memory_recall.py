from io import StringIO
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from backend.database.models.core import Competition, CompetitionSeason
from backend.database.models.reporting import Generation


def _config(database_url: str, *, output_buffer: StringIO | None = None) -> Config:
    root = Path(__file__).resolve().parents[4]
    config = Config(
        str(root / "backend" / "migrations" / "alembic.ini"),
        output_buffer=output_buffer,
    )
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def test_generation_memory_recall_upgrade_and_downgrade_compile_offline() -> None:
    upgrade_sql = StringIO()
    command.upgrade(
        _config(
            "postgresql+psycopg://unused:unused@localhost/unused",
            output_buffer=upgrade_sql,
        ),
        "0011",
        sql=True,
    )
    upgrade = upgrade_sql.getvalue()
    assert "CREATE TABLE reporting.generation_memory_recalls" in upgrade
    assert "result_jsonb JSONB NOT NULL" in upgrade
    assert "metadata_jsonb JSONB DEFAULT '{}'::jsonb NOT NULL" in upgrade
    assert "generation_memory_recalls_append_only" in upgrade

    downgrade_sql = StringIO()
    command.downgrade(
        _config(
            "postgresql+psycopg://unused:unused@localhost/unused",
            output_buffer=downgrade_sql,
        ),
        "0011:0010",
        sql=True,
    )
    downgrade = downgrade_sql.getvalue()
    assert "DROP FUNCTION reporting.reject_generation_memory_recall_mutation()" in downgrade
    assert "DROP TABLE reporting.generation_memory_recalls" in downgrade


def test_generation_memory_recall_upgrade_is_additive_and_immutable(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIDAM_MIGRATION_REQUIRE_TLS", "false")
    monkeypatch.setenv("AIDAM_MIGRATION_ROLE", "aidam_owner")
    config = _config(database_url)
    command.upgrade(config, "0010")
    competition_id = uuid4()
    season_id = uuid4()
    legacy_generation_id = uuid4()
    recalled_generation_id = uuid4()
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            {"id": competition_id, "display_name": "Recall Migration League"},
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
        for generation_id in (legacy_generation_id, recalled_generation_id):
            connection.execute(
                sa.insert(Generation),
                {
                    "id": generation_id,
                    "competition_id": competition_id,
                    "competition_season_id": season_id,
                    "kind": "live",
                    "status": "running",
                    "request_text": "write the recap",
                    "requested_primary_model": "test-model",
                    "settings_jsonb": {},
                },
            )

    command.upgrade(config, "0011")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO reporting.generation_memory_recalls (
                    generation_id, status, result_jsonb, result_text
                ) VALUES (
                    :generation_id, 'complete', CAST(:result AS jsonb), :result_text
                )
                """
            ),
            {
                "generation_id": recalled_generation_id,
                "result": '{"partial": false}',
                "result_text": '{"partial":false}',
            },
        )
        rows = connection.execute(
            text(
                "SELECT generation_id, result_jsonb, result_text, metadata_jsonb "
                "FROM reporting.generation_memory_recalls"
            )
        ).mappings().all()

    assert len(rows) == 1
    assert rows[0]["generation_id"] == recalled_generation_id
    assert rows[0]["result_jsonb"] == {"partial": False}
    assert rows[0]["result_text"] == '{"partial":false}'
    assert rows[0]["metadata_jsonb"] == {}
    with pytest.raises(DBAPIError, match="memory recall records are immutable"):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE reporting.generation_memory_recalls "
                    "SET result_text = 'changed' WHERE generation_id = :id"
                ),
                {"id": recalled_generation_id},
            )

    command.downgrade(config, "0010")
    assert "generation_memory_recalls" not in inspect(engine).get_table_names(
        schema="reporting"
    )
    command.upgrade(config, "0011")
    command.downgrade(config, "base")
    engine.dispose()
