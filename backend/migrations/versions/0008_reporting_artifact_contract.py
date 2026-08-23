"""Align reporting artifacts with the file-like artifact contract.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_legacy_artifact_guard() -> None:
    op.execute("DROP FUNCTION reporting.protect_artifact_version() CASCADE")


def _create_artifact_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION reporting.protect_artifact()
        RETURNS trigger LANGUAGE plpgsql AS $reporting$
        DECLARE
            selected_revision smallint;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'artifact identities cannot be deleted';
            END IF;

            IF ROW(
                NEW.id, NEW.generation_id, NEW.path,
                NEW.media_type, NEW.created_at
            ) IS DISTINCT FROM ROW(
                OLD.id, OLD.generation_id, OLD.path,
                OLD.media_type, OLD.created_at
            ) THEN
                RAISE EXCEPTION 'artifact identity is immutable';
            END IF;

            IF OLD.finalized_version_id IS NOT NULL
               AND ROW(NEW.finalized_version_id, NEW.finalized_at)
                   IS DISTINCT FROM
                   ROW(OLD.finalized_version_id, OLD.finalized_at) THEN
                RAISE EXCEPTION 'artifact finalization is immutable';
            END IF;

            IF OLD.finalized_version_id IS NULL
               AND NEW.finalized_version_id IS NOT NULL THEN
                SELECT revision_number INTO selected_revision
                FROM reporting.artifact_versions
                WHERE id = NEW.finalized_version_id
                  AND artifact_id = NEW.id
                  AND generation_id = NEW.generation_id;

                IF selected_revision IS NULL THEN
                    RAISE EXCEPTION 'finalized version must belong to the artifact';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM reporting.artifact_versions
                    WHERE artifact_id = NEW.id
                      AND revision_number > selected_revision
                ) THEN
                    RAISE EXCEPTION 'only the latest artifact version can be finalized';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $reporting$
        """
    )
    op.execute(
        """
        CREATE TRIGGER artifacts_protect_identity_and_finalization
        BEFORE UPDATE OR DELETE ON reporting.artifacts
        FOR EACH ROW EXECUTE FUNCTION reporting.protect_artifact()
        """
    )
    op.execute(
        """
        CREATE FUNCTION reporting.protect_artifact_version()
        RETURNS trigger LANGUAGE plpgsql AS $reporting$
        DECLARE
            artifact_finalized_version_id uuid;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'artifact versions are append-only';
            END IF;

            SELECT finalized_version_id INTO artifact_finalized_version_id
            FROM reporting.artifacts
            WHERE id = NEW.artifact_id
              AND generation_id = NEW.generation_id
            FOR UPDATE;

            IF FOUND AND artifact_finalized_version_id IS NOT NULL THEN
                RAISE EXCEPTION 'finalized artifacts cannot accept new versions';
            END IF;

            RETURN NEW;
        END;
        $reporting$
        """
    )
    op.execute(
        """
        CREATE TRIGGER artifact_versions_append_only
        BEFORE INSERT OR UPDATE OR DELETE ON reporting.artifact_versions
        FOR EACH ROW EXECUTE FUNCTION reporting.protect_artifact_version()
        """
    )


def _drop_artifact_guards() -> None:
    op.execute("DROP FUNCTION reporting.protect_artifact_version() CASCADE")
    op.execute("DROP FUNCTION reporting.protect_artifact() CASCADE")


def _create_legacy_artifact_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION reporting.protect_artifact_version()
        RETURNS trigger LANGUAGE plpgsql AS $reporting$
        BEGIN
            RAISE EXCEPTION 'artifact versions are append-only';
        END;
        $reporting$
        """
    )
    op.execute(
        """
        CREATE TRIGGER artifact_versions_append_only
        BEFORE UPDATE OR DELETE ON reporting.artifact_versions
        FOR EACH ROW EXECUTE FUNCTION reporting.protect_artifact_version()
        """
    )


def upgrade() -> None:
    _drop_legacy_artifact_guard()

    op.add_column(
        "artifacts", sa.Column("path", sa.Text(), nullable=True), schema="reporting"
    )
    op.add_column(
        "artifacts",
        sa.Column("media_type", sa.Text(), nullable=True),
        schema="reporting",
    )
    op.add_column(
        "artifacts",
        sa.Column("finalized_version_id", sa.UUID(), nullable=True),
        schema="reporting",
    )
    op.add_column(
        "artifacts",
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        schema="reporting",
    )
    op.execute(
        """
        UPDATE reporting.artifacts
        SET path = kind || '/' || name,
            media_type = CASE lower(format)
                WHEN 'markdown' THEN 'text/markdown'
                WHEN 'json' THEN 'application/json'
                WHEN 'text' THEN 'text/plain'
                ELSE format
            END
        """
    )
    op.alter_column("artifacts", "path", nullable=False, schema="reporting")
    op.alter_column("artifacts", "media_type", nullable=False, schema="reporting")

    op.create_unique_constraint(
        "uq_artifact_versions_id_artifact_generation",
        "artifact_versions",
        ["id", "artifact_id", "generation_id"],
        schema="reporting",
    )
    op.execute(
        """
        UPDATE reporting.artifacts AS artifact
        SET finalized_version_id = version.id,
            finalized_at = version.created_at
        FROM reporting.artifact_versions AS version
        WHERE version.artifact_id = artifact.id
          AND version.generation_id = artifact.generation_id
          AND version.status = 'final'
        """
    )
    op.create_check_constraint(
        op.f("ck_artifacts_finalization_shape"),
        "artifacts",
        "(finalized_version_id IS NULL) = (finalized_at IS NULL)",
        schema="reporting",
    )
    op.create_foreign_key(
        "fk_artifacts_finalized_version_same_artifact",
        "artifacts",
        "artifact_versions",
        ["finalized_version_id", "id", "generation_id"],
        ["id", "artifact_id", "generation_id"],
        source_schema="reporting",
        referent_schema="reporting",
        ondelete="RESTRICT",
    )

    op.drop_index(
        "uq_artifact_versions_one_final",
        table_name="artifact_versions",
        schema="reporting",
        postgresql_where=sa.text("status = 'final'"),
    )
    op.drop_index(
        "ix_artifact_versions_final",
        table_name="artifact_versions",
        schema="reporting",
        postgresql_where=sa.text("status = 'final'"),
    )
    op.drop_column("artifact_versions", "status", schema="reporting")

    op.drop_index(
        "ix_artifacts_generation_kind",
        table_name="artifacts",
        schema="reporting",
    )
    op.drop_constraint(
        "uq_artifacts_generation_kind_name",
        "artifacts",
        type_="unique",
        schema="reporting",
    )
    op.create_unique_constraint(
        "uq_artifacts_generation_path",
        "artifacts",
        ["generation_id", "path"],
        schema="reporting",
    )
    op.create_index(
        "ix_artifacts_generation_path",
        "artifacts",
        ["generation_id", "path"],
        schema="reporting",
    )
    op.drop_column("artifacts", "format", schema="reporting")
    op.drop_column("artifacts", "name", schema="reporting")
    op.drop_column("artifacts", "kind", schema="reporting")

    _create_artifact_guards()


def downgrade() -> None:
    _drop_artifact_guards()

    op.add_column(
        "artifacts", sa.Column("kind", sa.Text(), nullable=True), schema="reporting"
    )
    op.add_column(
        "artifacts", sa.Column("name", sa.Text(), nullable=True), schema="reporting"
    )
    op.add_column(
        "artifacts", sa.Column("format", sa.Text(), nullable=True), schema="reporting"
    )
    op.execute(
        """
        UPDATE reporting.artifacts
        SET kind = CASE
                WHEN strpos(path, '/') > 0 THEN split_part(path, '/', 1)
                ELSE 'artifact'
            END,
            name = CASE
                WHEN strpos(path, '/') > 0
                    THEN substring(path FROM strpos(path, '/') + 1)
                ELSE path
            END,
            format = CASE media_type
                WHEN 'text/markdown' THEN 'markdown'
                WHEN 'application/json' THEN 'json'
                WHEN 'text/plain' THEN 'text'
                ELSE media_type
            END
        """
    )
    op.alter_column("artifacts", "kind", nullable=False, schema="reporting")
    op.alter_column("artifacts", "name", nullable=False, schema="reporting")
    op.alter_column("artifacts", "format", nullable=False, schema="reporting")

    op.add_column(
        "artifact_versions",
        sa.Column("status", sa.Text(), nullable=True),
        schema="reporting",
    )
    op.execute("UPDATE reporting.artifact_versions SET status = 'working'")
    op.execute(
        """
        UPDATE reporting.artifact_versions AS version
        SET status = 'final'
        FROM reporting.artifacts AS artifact
        WHERE artifact.finalized_version_id = version.id
          AND artifact.id = version.artifact_id
          AND artifact.generation_id = version.generation_id
        """
    )
    op.alter_column(
        "artifact_versions", "status", nullable=False, schema="reporting"
    )

    op.drop_constraint(
        "fk_artifacts_finalized_version_same_artifact",
        "artifacts",
        type_="foreignkey",
        schema="reporting",
    )
    op.drop_constraint(
        op.f("ck_artifacts_finalization_shape"),
        "artifacts",
        type_="check",
        schema="reporting",
    )
    op.drop_constraint(
        "uq_artifact_versions_id_artifact_generation",
        "artifact_versions",
        type_="unique",
        schema="reporting",
    )
    op.drop_column("artifacts", "finalized_at", schema="reporting")
    op.drop_column("artifacts", "finalized_version_id", schema="reporting")

    op.drop_index(
        "ix_artifacts_generation_path",
        table_name="artifacts",
        schema="reporting",
    )
    op.drop_constraint(
        "uq_artifacts_generation_path",
        "artifacts",
        type_="unique",
        schema="reporting",
    )
    op.create_unique_constraint(
        "uq_artifacts_generation_kind_name",
        "artifacts",
        ["generation_id", "kind", "name"],
        schema="reporting",
    )
    op.create_index(
        "ix_artifacts_generation_kind",
        "artifacts",
        ["generation_id", "kind"],
        schema="reporting",
    )
    op.drop_column("artifacts", "media_type", schema="reporting")
    op.drop_column("artifacts", "path", schema="reporting")

    op.create_index(
        "ix_artifact_versions_final",
        "artifact_versions",
        ["artifact_id"],
        schema="reporting",
        postgresql_where=sa.text("status = 'final'"),
    )
    op.create_index(
        "uq_artifact_versions_one_final",
        "artifact_versions",
        ["artifact_id"],
        unique=True,
        schema="reporting",
        postgresql_where=sa.text("status = 'final'"),
    )

    _create_legacy_artifact_guard()
