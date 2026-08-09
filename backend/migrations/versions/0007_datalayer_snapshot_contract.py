"""Align frozen snapshot persistence with the datalayer service contract.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_snapshot_guards() -> None:
    op.execute("DROP FUNCTION sleeper.protect_snapshot_request_membership() CASCADE")
    op.execute("DROP FUNCTION sleeper.protect_sealed_data_snapshot() CASCADE")


def _create_snapshot_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION sleeper.protect_sealed_data_snapshot()
        RETURNS trigger LANGUAGE plpgsql AS $aida$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.status IN ('ready', 'expired') THEN
                    RAISE EXCEPTION 'sealed Sleeper data snapshots cannot be deleted';
                END IF;
                RETURN OLD;
            END IF;

            IF OLD.status = 'expired' AND NEW IS DISTINCT FROM OLD THEN
                RAISE EXCEPTION 'expired Sleeper data snapshots are terminal';
            END IF;

            IF OLD.status = 'ready' THEN
                IF NEW.status NOT IN ('ready', 'expired')
                   OR ROW(
                       NEW.competition_id, NEW.primary_competition_season_id,
                       NEW.build_key, NEW.domain_cutoff_week, NEW.domain_cutoff_at,
                       NEW.observed_through, NEW.snapshot_projection_version,
                       NEW.code_version, NEW.completeness_warnings,
                       NEW.failure_summary, NEW.selected_request_set_sha256,
                       NEW.sqlite_artifact_sha256,
                       NEW.sqlite_artifact_byte_length,
                       NEW.sqlite_artifact_storage_key, NEW.created_at,
                       NEW.completed_at
                   ) IS DISTINCT FROM ROW(
                       OLD.competition_id, OLD.primary_competition_season_id,
                       OLD.build_key, OLD.domain_cutoff_week, OLD.domain_cutoff_at,
                       OLD.observed_through, OLD.snapshot_projection_version,
                       OLD.code_version, OLD.completeness_warnings,
                       OLD.failure_summary, OLD.selected_request_set_sha256,
                       OLD.sqlite_artifact_sha256,
                       OLD.sqlite_artifact_byte_length,
                       OLD.sqlite_artifact_storage_key, OLD.created_at,
                       OLD.completed_at
                   ) THEN
                    RAISE EXCEPTION 'sealed Sleeper data snapshot meaning is immutable';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $aida$
        """
    )
    op.execute(
        """
        CREATE TRIGGER data_snapshots_protect_sealed
        BEFORE UPDATE OR DELETE ON sleeper.data_snapshots
        FOR EACH ROW EXECUTE FUNCTION sleeper.protect_sealed_data_snapshot()
        """
    )
    op.execute(
        """
        CREATE FUNCTION sleeper.protect_snapshot_request_membership()
        RETURNS trigger LANGUAGE plpgsql AS $aida$
        DECLARE
            snapshot_status text;
            snapshot_season_id uuid;
            request_season_id uuid;
        BEGIN
            IF TG_OP IN ('UPDATE', 'DELETE') THEN
                SELECT status INTO snapshot_status
                FROM sleeper.data_snapshots
                WHERE id = OLD.data_snapshot_id;
                IF snapshot_status IN ('ready', 'expired') THEN
                    RAISE EXCEPTION 'sealed data snapshot request membership is immutable';
                END IF;
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;

            SELECT status, primary_competition_season_id
            INTO snapshot_status, snapshot_season_id
            FROM sleeper.data_snapshots
            WHERE id = NEW.data_snapshot_id
            FOR UPDATE;
            IF snapshot_status IN ('ready', 'expired') THEN
                RAISE EXCEPTION 'sealed data snapshot request membership is immutable';
            END IF;

            SELECT competition_season_id INTO request_season_id
            FROM sleeper.api_requests
            WHERE id = NEW.api_request_id;
            IF request_season_id IS NOT NULL
               AND request_season_id <> snapshot_season_id THEN
                RAISE EXCEPTION 'snapshot request belongs to another competition season';
            END IF;
            RETURN NEW;
        END;
        $aida$
        """
    )
    op.execute(
        """
        CREATE TRIGGER data_snapshot_requests_protect_membership
        BEFORE INSERT OR UPDATE OR DELETE ON sleeper.data_snapshot_requests
        FOR EACH ROW EXECUTE FUNCTION sleeper.protect_snapshot_request_membership()
        """
    )


def _create_legacy_snapshot_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION sleeper.protect_sealed_data_snapshot()
        RETURNS trigger LANGUAGE plpgsql AS $aida$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.status IN ('ready', 'expired') THEN
                    RAISE EXCEPTION 'sealed Sleeper data snapshots cannot be deleted';
                END IF;
                RETURN OLD;
            END IF;

            IF OLD.status IN ('ready', 'expired') THEN
                IF NEW.status NOT IN ('ready', 'expired')
                   OR ROW(
                       NEW.competition_id, NEW.primary_competition_season_id,
                       NEW.mode, NEW.domain_cutoff_week, NEW.domain_cutoff_at,
                       NEW.knowledge_cutoff_at, NEW.materializer_version,
                       NEW.sqlite_schema_version, NEW.code_version,
                       NEW.completeness_warnings,
                       NEW.selected_request_set_sha256,
                       NEW.sqlite_artifact_sha256,
                       NEW.sqlite_artifact_byte_length,
                       NEW.sqlite_artifact_storage_key, NEW.created_at,
                       NEW.completed_at
                   ) IS DISTINCT FROM ROW(
                       OLD.competition_id, OLD.primary_competition_season_id,
                       OLD.mode, OLD.domain_cutoff_week, OLD.domain_cutoff_at,
                       OLD.knowledge_cutoff_at, OLD.materializer_version,
                       OLD.sqlite_schema_version, OLD.code_version,
                       OLD.completeness_warnings,
                       OLD.selected_request_set_sha256,
                       OLD.sqlite_artifact_sha256,
                       OLD.sqlite_artifact_byte_length,
                       OLD.sqlite_artifact_storage_key, OLD.created_at,
                       OLD.completed_at
                   ) THEN
                    RAISE EXCEPTION 'sealed Sleeper data snapshot meaning is immutable';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $aida$
        """
    )
    op.execute(
        """
        CREATE TRIGGER data_snapshots_protect_sealed
        BEFORE UPDATE OR DELETE ON sleeper.data_snapshots
        FOR EACH ROW EXECUTE FUNCTION sleeper.protect_sealed_data_snapshot()
        """
    )
    op.execute(
        """
        CREATE FUNCTION sleeper.protect_snapshot_request_membership()
        RETURNS trigger LANGUAGE plpgsql AS $aida$
        DECLARE
            snapshot_status text;
            snapshot_season_id uuid;
            request_season_id uuid;
        BEGIN
            IF TG_OP IN ('UPDATE', 'DELETE') THEN
                SELECT status INTO snapshot_status
                FROM sleeper.data_snapshots
                WHERE id = OLD.data_snapshot_id;
                IF snapshot_status IN ('ready', 'expired') THEN
                    RAISE EXCEPTION 'sealed data snapshot request membership is immutable';
                END IF;
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;

            SELECT status, primary_competition_season_id
            INTO snapshot_status, snapshot_season_id
            FROM sleeper.data_snapshots
            WHERE id = NEW.data_snapshot_id
            FOR UPDATE;
            IF snapshot_status IN ('ready', 'expired') THEN
                RAISE EXCEPTION 'sealed data snapshot request membership is immutable';
            END IF;

            SELECT competition_season_id INTO request_season_id
            FROM sleeper.api_requests
            WHERE id = NEW.api_request_id;
            IF request_season_id IS NOT NULL
               AND request_season_id <> snapshot_season_id THEN
                RAISE EXCEPTION 'snapshot request belongs to another competition season';
            END IF;
            RETURN NEW;
        END;
        $aida$
        """
    )
    op.execute(
        """
        CREATE TRIGGER data_snapshot_requests_protect_membership
        BEFORE INSERT OR UPDATE OR DELETE ON sleeper.data_snapshot_requests
        FOR EACH ROW EXECUTE FUNCTION sleeper.protect_snapshot_request_membership()
        """
    )


def upgrade() -> None:
    _drop_snapshot_guards()

    op.add_column(
        "data_snapshots",
        sa.Column("build_key", sa.Text(), nullable=True),
        schema="sleeper",
    )
    op.execute(
        "UPDATE sleeper.data_snapshots "
        "SET build_key = 'legacy:' || id::text WHERE build_key IS NULL"
    )
    op.alter_column("data_snapshots", "build_key", nullable=False, schema="sleeper")

    op.drop_index(
        "ix_data_snapshots_season_mode_cutoff_created",
        table_name="data_snapshots",
        schema="sleeper",
    )
    op.alter_column(
        "data_snapshots",
        "knowledge_cutoff_at",
        new_column_name="observed_through",
        schema="sleeper",
    )
    op.alter_column(
        "data_snapshots",
        "materializer_version",
        new_column_name="snapshot_projection_version",
        schema="sleeper",
    )
    op.drop_column("data_snapshots", "sqlite_schema_version", schema="sleeper")
    op.drop_column("data_snapshots", "mode", schema="sleeper")
    op.add_column(
        "data_snapshots",
        sa.Column(
            "failure_summary",
            postgresql.JSONB(astext_type=Text()),
            nullable=True,
        ),
        schema="sleeper",
    )
    op.create_index(
        "ix_data_snapshots_season_cutoff_created",
        "data_snapshots",
        ["primary_competition_season_id", "observed_through", "created_at"],
        schema="sleeper",
    )
    op.create_index(
        "uq_data_snapshots_active_build_key",
        "data_snapshots",
        ["build_key"],
        unique=True,
        schema="sleeper",
        postgresql_where=sa.text("status IN ('building', 'ready')"),
    )

    op.add_column(
        "data_snapshot_requests",
        sa.Column("response_sha256", sa.Text(), nullable=True),
        schema="sleeper",
    )
    op.execute(
        """
        UPDATE sleeper.data_snapshot_requests AS membership
        SET response_sha256 = request.response_sha256
        FROM sleeper.api_requests AS request
        WHERE request.id = membership.api_request_id
        """
    )
    op.alter_column(
        "data_snapshot_requests",
        "response_sha256",
        nullable=False,
        schema="sleeper",
    )
    op.drop_constraint(
        "fk_data_snapshot_requests_request_scope",
        "data_snapshot_requests",
        type_="foreignkey",
        schema="sleeper",
    )
    op.create_foreign_key(
        "fk_data_snapshot_requests_request_scope_hash",
        "data_snapshot_requests",
        "api_requests",
        ["api_request_id", "scope_key", "response_sha256"],
        ["id", "scope_key", "response_sha256"],
        source_schema="sleeper",
        referent_schema="sleeper",
        ondelete="RESTRICT",
    )

    _create_snapshot_guards()


def downgrade() -> None:
    _drop_snapshot_guards()

    op.drop_constraint(
        "fk_data_snapshot_requests_request_scope_hash",
        "data_snapshot_requests",
        type_="foreignkey",
        schema="sleeper",
    )
    op.create_foreign_key(
        "fk_data_snapshot_requests_request_scope",
        "data_snapshot_requests",
        "api_requests",
        ["api_request_id", "scope_key"],
        ["id", "scope_key"],
        source_schema="sleeper",
        referent_schema="sleeper",
        ondelete="RESTRICT",
    )
    op.drop_column("data_snapshot_requests", "response_sha256", schema="sleeper")

    op.drop_index(
        "uq_data_snapshots_active_build_key",
        table_name="data_snapshots",
        schema="sleeper",
    )
    op.drop_index(
        "ix_data_snapshots_season_cutoff_created",
        table_name="data_snapshots",
        schema="sleeper",
    )
    op.drop_column("data_snapshots", "failure_summary", schema="sleeper")
    op.add_column(
        "data_snapshots",
        sa.Column("mode", sa.Text(), nullable=True),
        schema="sleeper",
    )
    op.execute("UPDATE sleeper.data_snapshots SET mode = 'legacy' WHERE mode IS NULL")
    op.alter_column("data_snapshots", "mode", nullable=False, schema="sleeper")
    op.add_column(
        "data_snapshots",
        sa.Column("sqlite_schema_version", sa.Text(), nullable=True),
        schema="sleeper",
    )
    op.execute(
        "UPDATE sleeper.data_snapshots "
        "SET sqlite_schema_version = snapshot_projection_version"
    )
    op.alter_column(
        "data_snapshots",
        "sqlite_schema_version",
        nullable=False,
        schema="sleeper",
    )
    op.alter_column(
        "data_snapshots",
        "snapshot_projection_version",
        new_column_name="materializer_version",
        schema="sleeper",
    )
    op.alter_column(
        "data_snapshots",
        "observed_through",
        new_column_name="knowledge_cutoff_at",
        schema="sleeper",
    )
    op.create_index(
        "ix_data_snapshots_season_mode_cutoff_created",
        "data_snapshots",
        [
            "primary_competition_season_id",
            "mode",
            "knowledge_cutoff_at",
            "created_at",
        ],
        schema="sleeper",
    )
    op.drop_column("data_snapshots", "build_key", schema="sleeper")

    _create_legacy_snapshot_guards()
