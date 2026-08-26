"""Add multi-season snapshot membership and automatic refresh claims.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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


def downgrade() -> None:
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
