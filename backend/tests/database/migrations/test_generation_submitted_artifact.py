from io import StringIO
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from backend.database.models.core import Competition, CompetitionSeason
from backend.database.models.reporting import Artifact, ArtifactVersion, Generation


def _config(database_url: str, *, output_buffer: StringIO | None = None) -> Config:
    root = Path(__file__).resolve().parents[4]
    config = Config(
        str(root / "backend" / "migrations" / "alembic.ini"),
        output_buffer=output_buffer,
    )
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def test_submitted_artifact_upgrade_and_downgrade_compile_offline() -> None:
    upgrade_sql = StringIO()
    command.upgrade(
        _config(
            "postgresql+psycopg://unused:unused@localhost/unused",
            output_buffer=upgrade_sql,
        ),
        "0009",
        sql=True,
    )
    upgrade = upgrade_sql.getvalue()
    assert "submitted_artifact_version_id" in upgrade
    assert "fk_generations_submitted_artifact_finalized" in upgrade
    assert "ix_generations_competition_submitted_completed" in upgrade

    downgrade_sql = StringIO()
    command.downgrade(
        _config(
            "postgresql+psycopg://unused:unused@localhost/unused",
            output_buffer=downgrade_sql,
        ),
        "0009:0008",
        sql=True,
    )
    downgrade = downgrade_sql.getvalue()
    assert "DROP COLUMN submitted_artifact_version_id" in downgrade
    assert "DROP CONSTRAINT uq_artifacts_finalized_version_generation" in downgrade


def test_submitted_artifact_migration_pins_only_a_finalized_owned_version(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIDAM_MIGRATION_REQUIRE_TLS", "false")
    monkeypatch.setenv("AIDAM_MIGRATION_ROLE", "aidam_owner")
    config = _config(database_url)
    command.upgrade(config, "0008")

    competition_id = uuid4()
    season_id = uuid4()
    generation_id = uuid4()
    artifact_id = uuid4()
    version_id = uuid4()
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            {"id": competition_id, "display_name": "Output Migration League"},
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
            sa.insert(Artifact),
            {
                "id": artifact_id,
                "generation_id": generation_id,
                "path": "drafts/week-8-recap.md",
                "media_type": "text/markdown",
            },
        )
        connection.execute(
            sa.insert(ArtifactVersion),
            {
                "id": version_id,
                "artifact_id": artifact_id,
                "generation_id": generation_id,
                "revision_number": 1,
                "content": "# Week 8",
                "content_hash": (
                    "6322952fade5927c26fd1a800285fbfb80a0a87ae5191b7b1096a83c793b399e"
                ),
            },
        )

    command.upgrade(config, "0009")
    generation_columns = {
        column["name"]
        for column in inspect(engine).get_columns(
            "generations", schema="reporting"
        )
    }
    assert "submitted_artifact_version_id" in generation_columns

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.update(Generation)
            .where(Generation.id == generation_id)
            .values(
                status="succeeded",
                submitted_artifact_version_id=version_id,
                completed_at=sa.func.now(),
            )
        )

    with engine.begin() as connection:
        connection.execute(
            sa.update(Artifact)
            .where(Artifact.id == artifact_id)
            .values(
                finalized_version_id=version_id,
                finalized_at=sa.func.now(),
            )
        )
        connection.execute(
            sa.update(Generation)
            .where(Generation.id == generation_id)
            .values(
                status="succeeded",
                submitted_artifact_version_id=version_id,
                completed_at=sa.func.now(),
            )
        )

    with engine.connect() as connection:
        submitted = connection.scalar(
            sa.select(Generation.submitted_artifact_version_id).where(
                Generation.id == generation_id
            )
        )
    assert submitted == version_id

    command.downgrade(config, "0008")
    downgraded_columns = {
        column["name"]
        for column in inspect(engine).get_columns(
            "generations", schema="reporting"
        )
    }
    assert "submitted_artifact_version_id" not in downgraded_columns

    command.upgrade(config, "0009")
    command.downgrade(config, "base")
    engine.dispose()
