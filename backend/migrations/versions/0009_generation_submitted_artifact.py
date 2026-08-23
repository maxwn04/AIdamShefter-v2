"""Attach the reporter-selected finalized artifact version to its generation.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_artifacts_finalized_version_generation",
        "artifacts",
        ["finalized_version_id", "generation_id"],
        schema="reporting",
    )
    op.add_column(
        "generations",
        sa.Column("submitted_artifact_version_id", sa.UUID(), nullable=True),
        schema="reporting",
    )
    op.create_check_constraint(
        op.f("ck_generations_submitted_artifact_shape"),
        "generations",
        "submitted_artifact_version_id IS NULL OR status = 'succeeded'",
        schema="reporting",
    )
    op.create_foreign_key(
        "fk_generations_submitted_artifact_finalized",
        "generations",
        "artifacts",
        ["submitted_artifact_version_id", "id"],
        ["finalized_version_id", "generation_id"],
        source_schema="reporting",
        referent_schema="reporting",
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_generations_competition_submitted_completed",
        "generations",
        [
            "competition_id",
            sa.literal_column("completed_at DESC"),
            sa.literal_column("id DESC"),
        ],
        schema="reporting",
        postgresql_where=sa.text(
            "status = 'succeeded' "
            "AND submitted_artifact_version_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_generations_competition_submitted_completed",
        table_name="generations",
        schema="reporting",
        postgresql_where=sa.text(
            "status = 'succeeded' "
            "AND submitted_artifact_version_id IS NOT NULL"
        ),
    )
    op.drop_constraint(
        "fk_generations_submitted_artifact_finalized",
        "generations",
        type_="foreignkey",
        schema="reporting",
    )
    op.drop_constraint(
        op.f("ck_generations_submitted_artifact_shape"),
        "generations",
        type_="check",
        schema="reporting",
    )
    op.drop_column(
        "generations",
        "submitted_artifact_version_id",
        schema="reporting",
    )
    op.drop_constraint(
        "uq_artifacts_finalized_version_generation",
        "artifacts",
        type_="unique",
        schema="reporting",
    )
