"""Create the core identity schema.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "competitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_competitions"),
        schema="core",
    )

    op.create_table(
        "competition_seasons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("season_year", sa.SmallInteger(), nullable=False),
        sa.Column("sequence_number", sa.SmallInteger(), nullable=False),
        sa.Column("sleeper_league_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["competition_id"],
            ["core.competitions.id"],
            name="fk_competition_seasons_competition_id_competitions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_competition_seasons"),
        sa.UniqueConstraint(
            "competition_id",
            "season_year",
            name="uq_competition_seasons_competition_id_season_year",
        ),
        sa.UniqueConstraint(
            "competition_id",
            "sequence_number",
            name="uq_competition_seasons_competition_id_sequence_number",
        ),
        sa.UniqueConstraint(
            "id",
            "competition_id",
            name="uq_competition_seasons_id_competition_id",
        ),
        sa.UniqueConstraint(
            "sleeper_league_id",
            name="uq_competition_seasons_sleeper_league_id",
        ),
        schema="core",
    )

    op.create_table(
        "franchises",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["competition_id"],
            ["core.competitions.id"],
            name="fk_franchises_competition_id_competitions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_franchises"),
        sa.UniqueConstraint(
            "id",
            "competition_id",
            name="uq_franchises_id_competition_id",
        ),
        schema="core",
    )
    op.create_index(
        "ix_franchises_competition_id_archived_at",
        "franchises",
        ["competition_id", "archived_at"],
        unique=False,
        schema="core",
    )

    op.create_table(
        "season_rosters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "competition_season_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("franchise_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sleeper_roster_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["competition_id"],
            ["core.competitions.id"],
            name="fk_season_rosters_competition_id_competitions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["competition_season_id", "competition_id"],
            [
                "core.competition_seasons.id",
                "core.competition_seasons.competition_id",
            ],
            name="fk_season_rosters_season_competition_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["franchise_id", "competition_id"],
            ["core.franchises.id", "core.franchises.competition_id"],
            name="fk_season_rosters_franchise_competition_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_season_rosters"),
        sa.UniqueConstraint(
            "competition_season_id",
            "sleeper_roster_id",
            name="uq_season_rosters_competition_season_id_sleeper_roster_id",
        ),
        sa.UniqueConstraint(
            "competition_season_id",
            "franchise_id",
            name="uq_season_rosters_competition_season_id_franchise_id",
        ),
        sa.UniqueConstraint(
            "id",
            "competition_season_id",
            name="uq_season_rosters_id_competition_season_id",
        ),
        sa.UniqueConstraint(
            "id",
            "competition_id",
            name="uq_season_rosters_id_competition_id",
        ),
        schema="core",
    )
    op.create_index(
        "ix_season_rosters_competition_id",
        "season_rosters",
        ["competition_id"],
        unique=False,
        schema="core",
    )
    op.create_index(
        "ix_season_rosters_season_competition_scope",
        "season_rosters",
        ["competition_season_id", "competition_id"],
        unique=False,
        schema="core",
    )
    op.create_index(
        "ix_season_rosters_franchise_competition_scope",
        "season_rosters",
        ["franchise_id", "competition_id"],
        unique=False,
        schema="core",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_season_rosters_franchise_competition_scope",
        table_name="season_rosters",
        schema="core",
    )
    op.drop_index(
        "ix_season_rosters_season_competition_scope",
        table_name="season_rosters",
        schema="core",
    )
    op.drop_index(
        "ix_season_rosters_competition_id",
        table_name="season_rosters",
        schema="core",
    )
    op.drop_table("season_rosters", schema="core")
    op.drop_index(
        "ix_franchises_competition_id_archived_at",
        table_name="franchises",
        schema="core",
    )
    op.drop_table("franchises", schema="core")
    op.drop_table("competition_seasons", schema="core")
    op.drop_table("competitions", schema="core")
