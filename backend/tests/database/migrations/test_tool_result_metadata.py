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


def test_tool_result_metadata_upgrade_and_downgrade_compile_offline() -> None:
    upgrade_sql = StringIO()
    command.upgrade(
        _config(
            "postgresql+psycopg://unused:unused@localhost/unused",
            output_buffer=upgrade_sql,
        ),
        "0010",
        sql=True,
    )
    upgrade = upgrade_sql.getvalue()
    assert "ADD COLUMN result_jsonb JSONB" in upgrade
    assert "ADD COLUMN result_text TEXT" in upgrade
    assert "ADD COLUMN metadata_jsonb JSONB" in upgrade
    assert "DISABLE TRIGGER tool_calls_protect_terminal" in upgrade
    assert "ENABLE TRIGGER tool_calls_protect_terminal" in upgrade

    downgrade_sql = StringIO()
    command.downgrade(
        _config(
            "postgresql+psycopg://unused:unused@localhost/unused",
            output_buffer=downgrade_sql,
        ),
        "0010:0009",
        sql=True,
    )
    downgrade = downgrade_sql.getvalue()
    assert "DROP COLUMN metadata_jsonb" in downgrade
    assert "DROP COLUMN result_text" in downgrade
    assert "DROP COLUMN result_jsonb" in downgrade


def test_tool_result_metadata_migrates_legacy_rows_and_restores_protection(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIDAM_MIGRATION_REQUIRE_TLS", "false")
    monkeypatch.setenv("AIDAM_MIGRATION_ROLE", "aidam_owner")
    config = _config(database_url)
    command.upgrade(config, "0009")

    competition_id = uuid4()
    season_id = uuid4()
    generation_id = uuid4()
    ai_call_id = uuid4()
    structured_call_id = uuid4()
    text_call_id = uuid4()
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            {"id": competition_id, "display_name": "Tool Result Migration League"},
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
                "current_turn": 1,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO reporting.ai_calls (
                    id, generation_id, turn_number, attempt_number,
                    requested_model, input_messages, tool_definitions,
                    request_parameters, status, completed_at
                ) VALUES (
                    :id, :generation_id, 1, 0,
                    'test-model', '[]'::jsonb, '[]'::jsonb,
                    '{}'::jsonb, 'succeeded', pg_catalog.now()
                )
                """
            ),
            {"id": ai_call_id, "generation_id": generation_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO reporting.tool_calls (
                    id, generation_id, ai_call_id, tool_ordinal, tool_name,
                    implementation_version, arguments_jsonb, status,
                    full_result_text, structured_result_jsonb,
                    completed_at, duration_ms
                ) VALUES
                    (
                        :structured_id, :generation_id, :ai_call_id, 0,
                        'lookup', 'v1', '{}'::jsonb, 'succeeded',
                        :structured_text, CAST(:structured_result AS jsonb),
                        pg_catalog.now(), 1
                    ),
                    (
                        :text_id, :generation_id, :ai_call_id, 1,
                        'procedure', 'v1', '{}'::jsonb, 'succeeded',
                        '# Procedure', NULL, pg_catalog.now(), 1
                    )
                """
            ),
            {
                "structured_id": structured_call_id,
                "text_id": text_call_id,
                "generation_id": generation_id,
                "ai_call_id": ai_call_id,
                "structured_text": '{"found":true}',
                "structured_result": '{"found": true}',
            },
        )

    command.upgrade(config, "0010")
    with engine.connect() as connection:
        columns = {
            column["name"]
            for column in inspect(connection).get_columns(
                "tool_calls", schema="reporting"
            )
        }
        rows = connection.execute(
            text(
                """
                SELECT id, result_jsonb, result_text, metadata_jsonb
                FROM reporting.tool_calls
                WHERE generation_id = :generation_id
                ORDER BY tool_ordinal
                """
            ),
            {"generation_id": generation_id},
        ).mappings().all()

    assert {"result_jsonb", "result_text", "metadata_jsonb"} <= columns
    assert rows[0]["result_jsonb"] == {"found": True}
    assert rows[0]["result_text"] == '{"found":true}'
    assert rows[0]["metadata_jsonb"] == {}
    assert rows[1]["result_jsonb"] == "# Procedure"
    assert rows[1]["result_text"] == "# Procedure"
    assert rows[1]["metadata_jsonb"] == {}

    with pytest.raises(DBAPIError, match="terminal tool call records are immutable"):
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE reporting.tool_calls
                    SET result_text = 'changed'
                    WHERE id = :tool_call_id
                    """
                ),
                {"tool_call_id": structured_call_id},
            )

    command.downgrade(config, "0009")
    downgraded_columns = {
        column["name"]
        for column in inspect(engine).get_columns("tool_calls", schema="reporting")
    }
    assert {"result_jsonb", "result_text", "metadata_jsonb"}.isdisjoint(
        downgraded_columns
    )

    command.upgrade(config, "0010")
    command.downgrade(config, "base")
    engine.dispose()
