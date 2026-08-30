"""Add multi-season snapshot membership and automatic refresh claims.

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_snapshot_guards() -> None:
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "sleeper.protect_snapshot_season_membership() CASCADE"
    )
    op.execute("DROP FUNCTION sleeper.protect_snapshot_request_membership() CASCADE")
    op.execute("DROP FUNCTION sleeper.protect_sealed_data_snapshot() CASCADE")


def _create_multi_season_snapshot_guards() -> None:
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
                       NEW.id, NEW.competition_id,
                       NEW.primary_competition_season_id, NEW.build_key,
                       NEW.input_revision,
                       NEW.domain_cutoff_week, NEW.domain_cutoff_at,
                       NEW.as_of_date, NEW.snapshot_projection_version,
                       NEW.code_version, NEW.completeness_warnings,
                       NEW.failure_summary, NEW.sqlite_artifact_sha256,
                       NEW.sqlite_artifact_byte_length,
                       NEW.sqlite_artifact_storage_key, NEW.created_at,
                       NEW.completed_at
                   ) IS DISTINCT FROM ROW(
                       OLD.id, OLD.competition_id,
                       OLD.primary_competition_season_id, OLD.build_key,
                       OLD.input_revision,
                       OLD.domain_cutoff_week, OLD.domain_cutoff_at,
                       OLD.as_of_date, OLD.snapshot_projection_version,
                       OLD.code_version, OLD.completeness_warnings,
                       OLD.failure_summary, OLD.sqlite_artifact_sha256,
                       OLD.sqlite_artifact_byte_length,
                       OLD.sqlite_artifact_storage_key, OLD.created_at,
                       OLD.completed_at
                   ) THEN
                    RAISE EXCEPTION 'sealed Sleeper data snapshot meaning is immutable';
                END IF;
            END IF;

            IF NEW.status = 'ready' AND OLD.status <> 'ready' THEN
                IF (
                    SELECT count(*)
                    FROM sleeper.data_snapshot_seasons AS membership
                    WHERE membership.data_snapshot_id = NEW.id
                      AND membership.role = 'primary'
                      AND membership.competition_season_id =
                          NEW.primary_competition_season_id
                      AND membership.through_week = NEW.domain_cutoff_week
                ) <> 1 THEN
                    RAISE EXCEPTION 'ready snapshot requires one matching primary season';
                END IF;
                IF EXISTS (
                    SELECT 1
                    FROM sleeper.data_snapshot_requests AS membership
                    JOIN sleeper.api_requests AS request_row
                      ON request_row.id = membership.api_request_id
                    WHERE membership.data_snapshot_id = NEW.id
                      AND request_row.competition_season_id IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1
                          FROM sleeper.data_snapshot_seasons AS season_membership
                          WHERE season_membership.data_snapshot_id = NEW.id
                            AND season_membership.competition_season_id =
                                request_row.competition_season_id
                      )
                ) THEN
                    RAISE EXCEPTION 'snapshot request season is not sealed';
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
        CREATE FUNCTION sleeper.protect_snapshot_season_membership()
        RETURNS trigger LANGUAGE plpgsql AS $aida$
        DECLARE
            snapshot_status text;
        BEGIN
            IF TG_OP IN ('UPDATE', 'DELETE') THEN
                SELECT status INTO snapshot_status
                FROM sleeper.data_snapshots
                WHERE id = OLD.data_snapshot_id;
                IF snapshot_status IN ('ready', 'expired') THEN
                    RAISE EXCEPTION 'sealed data snapshot season membership is immutable';
                END IF;
                IF EXISTS (
                    SELECT 1
                    FROM sleeper.data_snapshot_requests AS membership
                    JOIN sleeper.api_requests AS request_row
                      ON request_row.id = membership.api_request_id
                    WHERE membership.data_snapshot_id = OLD.data_snapshot_id
                      AND request_row.competition_season_id =
                          OLD.competition_season_id
                ) THEN
                    RAISE EXCEPTION 'snapshot season membership is referenced';
                END IF;
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;

            SELECT status INTO snapshot_status
            FROM sleeper.data_snapshots
            WHERE id = NEW.data_snapshot_id
            FOR UPDATE;
            IF snapshot_status IN ('ready', 'expired') THEN
                RAISE EXCEPTION 'sealed data snapshot season membership is immutable';
            END IF;
            RETURN NEW;
        END;
        $aida$
        """
    )
    op.execute(
        """
        CREATE TRIGGER data_snapshot_seasons_protect_membership
        BEFORE INSERT OR UPDATE OR DELETE ON sleeper.data_snapshot_seasons
        FOR EACH ROW EXECUTE FUNCTION sleeper.protect_snapshot_season_membership()
        """
    )
    op.execute(
        """
        CREATE FUNCTION sleeper.protect_snapshot_request_membership()
        RETURNS trigger LANGUAGE plpgsql AS $aida$
        DECLARE
            snapshot_status text;
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

            SELECT status INTO snapshot_status
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
               AND NOT EXISTS (
                   SELECT 1
                   FROM sleeper.data_snapshot_seasons AS season_membership
                   WHERE season_membership.data_snapshot_id = NEW.data_snapshot_id
                     AND season_membership.competition_season_id = request_season_id
               ) THEN
                RAISE EXCEPTION 'snapshot request season is not included';
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


def _create_single_season_snapshot_guards() -> None:
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
                       NEW.id, NEW.competition_id,
                       NEW.primary_competition_season_id, NEW.build_key,
                       NEW.domain_cutoff_week, NEW.domain_cutoff_at,
                       NEW.as_of_date, NEW.snapshot_projection_version,
                       NEW.code_version, NEW.completeness_warnings,
                       NEW.failure_summary, NEW.sqlite_artifact_sha256,
                       NEW.sqlite_artifact_byte_length,
                       NEW.sqlite_artifact_storage_key, NEW.created_at,
                       NEW.completed_at
                   ) IS DISTINCT FROM ROW(
                       OLD.id, OLD.competition_id,
                       OLD.primary_competition_season_id, OLD.build_key,
                       OLD.domain_cutoff_week, OLD.domain_cutoff_at,
                       OLD.as_of_date, OLD.snapshot_projection_version,
                       OLD.code_version, OLD.completeness_warnings,
                       OLD.failure_summary, OLD.sqlite_artifact_sha256,
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
    op.add_column(
        "data_snapshots",
        sa.Column("input_revision", sa.Text(), nullable=True),
        schema="sleeper",
    )
    op.create_table(
        "data_snapshot_seasons",
        sa.Column("data_snapshot_id", sa.UUID(), nullable=False),
        sa.Column("competition_id", sa.UUID(), nullable=False),
        sa.Column("primary_competition_season_id", sa.UUID(), nullable=False),
        sa.Column("competition_season_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("through_week", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint(
            "role IN ('primary', 'history')",
            name=op.f("ck_data_snapshot_seasons_role"),
        ),
        sa.CheckConstraint(
            "through_week BETWEEN 1 AND 18",
            name=op.f("ck_data_snapshot_seasons_through_week"),
        ),
        sa.CheckConstraint(
            "role <> 'primary' OR "
            "competition_season_id = primary_competition_season_id",
            name=op.f("ck_data_snapshot_seasons_primary_matches"),
        ),
        sa.ForeignKeyConstraint(
            ["data_snapshot_id", "competition_id"],
            ["sleeper.data_snapshots.id", "sleeper.data_snapshots.competition_id"],
            name="fk_data_snapshot_seasons_snapshot_competition",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["data_snapshot_id", "primary_competition_season_id"],
            [
                "sleeper.data_snapshots.id",
                "sleeper.data_snapshots.primary_competition_season_id",
            ],
            name="fk_data_snapshot_seasons_snapshot_primary",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["competition_season_id", "competition_id"],
            ["core.competition_seasons.id", "core.competition_seasons.competition_id"],
            name="fk_data_snapshot_seasons_season_competition",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "data_snapshot_id",
            "competition_season_id",
            name=op.f("pk_data_snapshot_seasons"),
        ),
        schema="sleeper",
    )
    op.create_index(
        "uq_data_snapshot_seasons_primary",
        "data_snapshot_seasons",
        ["data_snapshot_id"],
        unique=True,
        schema="sleeper",
        postgresql_where=sa.text("role = 'primary'"),
    )
    op.create_index(
        "ix_data_snapshot_seasons_season_snapshot",
        "data_snapshot_seasons",
        ["competition_season_id", "data_snapshot_id"],
        schema="sleeper",
    )
    op.execute(
        """
        INSERT INTO sleeper.data_snapshot_seasons (
            data_snapshot_id,
            competition_id,
            primary_competition_season_id,
            competition_season_id,
            role,
            through_week
        )
        SELECT
            id,
            competition_id,
            primary_competition_season_id,
            primary_competition_season_id,
            'primary',
            domain_cutoff_week
        FROM sleeper.data_snapshots
        """
    )

    op.create_table(
        "automatic_refresh_claims",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("competition_id", sa.UUID(), nullable=False),
        sa.Column("competition_season_id", sa.UUID(), nullable=False),
        sa.Column("active_key", sa.Text(), nullable=False),
        sa.Column("requested_through_week", sa.SmallInteger(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("coverage_fingerprint", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("refresh_run_id", sa.UUID(), nullable=True),
        sa.Column("refresh_status", sa.Text(), nullable=True),
        sa.Column("failure_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "requested_through_week BETWEEN 1 AND 18",
            name=op.f("ck_automatic_refresh_claims_through_week"),
        ),
        sa.CheckConstraint(
            "reason IN ('missing', 'stale')",
            name=op.f("ck_automatic_refresh_claims_reason"),
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name=op.f("ck_automatic_refresh_claims_status"),
        ),
        sa.CheckConstraint(
            "(status = 'running' AND completed_at IS NULL "
            "AND refresh_run_id IS NULL AND refresh_status IS NULL "
            "AND failure_summary IS NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL "
            "AND refresh_run_id IS NOT NULL AND refresh_status IS NOT NULL "
            "AND failure_summary IS NULL) OR "
            "(status = 'failed' AND completed_at IS NOT NULL "
            "AND refresh_status IS NULL AND failure_summary IS NOT NULL)",
            name=op.f("ck_automatic_refresh_claims_terminal_shape"),
        ),
        sa.ForeignKeyConstraint(
            ["competition_season_id", "competition_id"],
            ["core.competition_seasons.id", "core.competition_seasons.competition_id"],
            name="fk_automatic_refresh_claims_season_competition",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["refresh_run_id", "competition_season_id"],
            ["sleeper.refresh_runs.id", "sleeper.refresh_runs.competition_season_id"],
            name="fk_automatic_refresh_claims_refresh_season",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_automatic_refresh_claims")),
        schema="sleeper",
    )
    op.create_index(
        "uq_automatic_refresh_claims_active_key",
        "automatic_refresh_claims",
        ["competition_id", "active_key"],
        unique=True,
        schema="sleeper",
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_index(
        "ix_automatic_refresh_claims_season_started",
        "automatic_refresh_claims",
        [
            "competition_season_id",
            "started_at",
        ],
        schema="sleeper",
    )
    _drop_snapshot_guards()
    _create_multi_season_snapshot_guards()


def downgrade() -> None:
    _drop_snapshot_guards()
    op.drop_index(
        "ix_automatic_refresh_claims_season_started",
        table_name="automatic_refresh_claims",
        schema="sleeper",
    )
    op.drop_index(
        "uq_automatic_refresh_claims_active_key",
        table_name="automatic_refresh_claims",
        schema="sleeper",
        postgresql_where=sa.text("status = 'running'"),
    )
    op.drop_table("automatic_refresh_claims", schema="sleeper")
    op.drop_index(
        "ix_data_snapshot_seasons_season_snapshot",
        table_name="data_snapshot_seasons",
        schema="sleeper",
    )
    op.drop_index(
        "uq_data_snapshot_seasons_primary",
        table_name="data_snapshot_seasons",
        schema="sleeper",
        postgresql_where=sa.text("role = 'primary'"),
    )
    op.drop_table("data_snapshot_seasons", schema="sleeper")
    op.drop_column("data_snapshots", "input_revision", schema="sleeper")
    _create_single_season_snapshot_guards()
