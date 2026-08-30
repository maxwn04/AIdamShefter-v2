"""Persist immutable generation-start memory recall telemetry.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generation_memory_recalls",
        sa.Column("generation_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "result_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("result_text", sa.Text(), nullable=False),
        sa.Column(
            "metadata_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('complete', 'partial', 'failed')",
            name=op.f("ck_generation_memory_recalls_status"),
        ),
        sa.ForeignKeyConstraint(
            ["generation_id"],
            ["reporting.generations.id"],
            name=op.f(
                "fk_generation_memory_recalls_generation_id_generations"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "generation_id",
            name=op.f("pk_generation_memory_recalls"),
        ),
        schema="reporting",
    )
    op.execute(
        """
        CREATE FUNCTION reporting.reject_generation_memory_recall_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'generation memory recall records are immutable';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER generation_memory_recalls_append_only
        BEFORE UPDATE OR DELETE ON reporting.generation_memory_recalls
        FOR EACH ROW
        EXECUTE FUNCTION reporting.reject_generation_memory_recall_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION reporting.reject_generation_memory_recall_mutation() CASCADE"
    )
    op.drop_table("generation_memory_recalls", schema="reporting")
