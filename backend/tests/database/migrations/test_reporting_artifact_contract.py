from io import StringIO
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text

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


def test_artifact_contract_upgrade_and_downgrade_compile_offline() -> None:
    upgrade_sql = StringIO()
    command.upgrade(
        _config(
            "postgresql+psycopg://unused:unused@localhost/unused",
            output_buffer=upgrade_sql,
        ),
        "0008",
        sql=True,
    )
    upgrade = upgrade_sql.getvalue()
    assert "ADD COLUMN path TEXT" in upgrade
    assert "ADD COLUMN media_type TEXT" in upgrade
    assert "finalized_version_id" in upgrade
    assert "fk_artifacts_finalized_version_same_artifact" in upgrade
    assert "artifacts_protect_identity_and_finalization" in upgrade

    downgrade_sql = StringIO()
    command.downgrade(
        _config(
            "postgresql+psycopg://unused:unused@localhost/unused",
            output_buffer=downgrade_sql,
        ),
        "0008:0007",
        sql=True,
    )
    downgrade = downgrade_sql.getvalue()
    assert "ADD COLUMN kind TEXT" in downgrade
    assert "ADD COLUMN status TEXT" in downgrade
    assert "uq_artifact_versions_one_final" in downgrade


def test_artifact_contract_migrates_legacy_rows_and_reverses(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIDAM_MIGRATION_REQUIRE_TLS", "false")
    monkeypatch.setenv("AIDAM_MIGRATION_ROLE", "aidam_owner")
    config = _config(database_url)
    command.upgrade(config, "0007")

    competition_id = uuid4()
    season_id = uuid4()
    generation_id = uuid4()
    article_id = uuid4()
    brief_id = uuid4()
    notes_id = uuid4()
    working_version_id = uuid4()
    final_version_id = uuid4()
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            {"id": competition_id, "display_name": "Artifact Migration League"},
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
                "status": "succeeded",
                "request_text": "write the report",
                "requested_primary_model": "test-model",
                "settings_jsonb": {},
                "current_turn": 1,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO reporting.artifacts (
                    id, generation_id, kind, name, format
                ) VALUES
                    (:article_id, :generation_id, 'article', 'main', 'markdown'),
                    (:brief_id, :generation_id, 'brief', 'main', 'json'),
                    (:notes_id, :generation_id, 'notes', 'main', 'text')
                """
            ),
            {
                "article_id": article_id,
                "brief_id": brief_id,
                "notes_id": notes_id,
                "generation_id": generation_id,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO reporting.artifact_versions (
                    id, artifact_id, generation_id, revision_number,
                    content, content_hash, status
                ) VALUES
                    (
                        :working_id, :artifact_id, :generation_id, 1,
                        '# Working', 'legacy-working-hash', 'working'
                    ),
                    (
                        :final_id, :artifact_id, :generation_id, 2,
                        '# Final', 'legacy-final-hash', 'final'
                    )
                """
            ),
            {
                "working_id": working_version_id,
                "final_id": final_version_id,
                "artifact_id": article_id,
                "generation_id": generation_id,
            },
        )

    command.upgrade(config, "0008")
    with engine.connect() as connection:
        artifact_columns = {
            column["name"]
            for column in inspect(connection).get_columns(
                "artifacts", schema="reporting"
            )
        }
        version_columns = {
            column["name"]
            for column in inspect(connection).get_columns(
                "artifact_versions", schema="reporting"
            )
        }
        rows = connection.execute(
            text(
                """
                SELECT id, path, media_type, finalized_version_id, finalized_at
                FROM reporting.artifacts
                WHERE generation_id = :generation_id
                ORDER BY path
                """
            ),
            {"generation_id": generation_id},
        ).mappings()
        artifacts = {row["id"]: row for row in rows}
        versions = connection.execute(
            text(
                """
                SELECT id, revision_number, content, content_hash
                FROM reporting.artifact_versions
                WHERE artifact_id = :artifact_id
                ORDER BY revision_number
                """
            ),
            {"artifact_id": article_id},
        ).all()

    assert {"path", "media_type", "finalized_version_id", "finalized_at"} <= (
        artifact_columns
    )
    assert {"kind", "name", "format"}.isdisjoint(artifact_columns)
    assert "status" not in version_columns
    assert artifacts[article_id]["path"] == "article/main"
    assert artifacts[article_id]["media_type"] == "text/markdown"
    assert artifacts[article_id]["finalized_version_id"] == final_version_id
    assert artifacts[article_id]["finalized_at"] is not None
    assert artifacts[brief_id]["media_type"] == "application/json"
    assert artifacts[notes_id]["media_type"] == "text/plain"
    assert versions == [
        (working_version_id, 1, "# Working", "legacy-working-hash"),
        (final_version_id, 2, "# Final", "legacy-final-hash"),
    ]

    command.downgrade(config, "0007")
    with engine.connect() as connection:
        legacy_artifact = connection.execute(
            text(
                """
                SELECT kind, name, format
                FROM reporting.artifacts
                WHERE id = :article_id
                """
            ),
            {"article_id": article_id},
        ).one()
        legacy_version_statuses = connection.execute(
            text(
                """
                SELECT id, revision_number, content, content_hash, status
                FROM reporting.artifact_versions
                WHERE artifact_id = :artifact_id
                ORDER BY revision_number
                """
            ),
            {"artifact_id": article_id},
        ).all()

    assert legacy_artifact == ("article", "main", "markdown")
    assert legacy_version_statuses == [
        (
            working_version_id,
            1,
            "# Working",
            "legacy-working-hash",
            "working",
        ),
        (final_version_id, 2, "# Final", "legacy-final-hash", "final"),
    ]

    command.upgrade(config, "0008")
    command.downgrade(config, "base")
    engine.dispose()
