"""Separate logical tool results from exact text and private metadata.

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
        "tool_calls",
        sa.Column(
            "result_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        schema="reporting",
    )
    op.add_column(
        "tool_calls",
        sa.Column("result_text", sa.Text(), nullable=True),
        schema="reporting",
    )
    op.add_column(
        "tool_calls",
        sa.Column(
            "metadata_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        schema="reporting",
    )

    # Existing terminal rows are protected from updates. Suspend the trigger only
    # for the deterministic compatibility backfill, then restore it in the same
    # transactional migration.
    op.execute(
        "ALTER TABLE reporting.tool_calls "
        "DISABLE TRIGGER tool_calls_protect_terminal"
    )
    op.execute(
        """
        UPDATE reporting.tool_calls
        SET result_jsonb = CASE
                WHEN structured_result_jsonb IS NOT NULL
                    THEN structured_result_jsonb
                WHEN full_result_text IS NOT NULL
                    THEN pg_catalog.to_jsonb(full_result_text)
                ELSE NULL
            END,
            result_text = full_result_text,
            metadata_jsonb = '{}'::jsonb
        """
    )
    op.execute(
        "ALTER TABLE reporting.tool_calls "
        "ENABLE TRIGGER tool_calls_protect_terminal"
    )


def downgrade() -> None:
    op.drop_column("tool_calls", "metadata_jsonb", schema="reporting")
    op.drop_column("tool_calls", "result_text", schema="reporting")
    op.drop_column("tool_calls", "result_jsonb", schema="reporting")
