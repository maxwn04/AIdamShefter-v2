"""Add rebuildable semantic memory vectors without changing canonical history.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_search_embeddings",
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("text_format_version", sa.Integer(), nullable=False),
        sa.Column("document_builder_version", sa.Integer(), nullable=False),
        sa.Column("source_content_hash", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.Text(), nullable=False),
        sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["memory.memory_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("version_id", "provider", "model", "dimensions", "text_format_version"),
        sa.CheckConstraint("dimensions > 0", name="positive_dimensions"),
        sa.CheckConstraint("cardinality(embedding) = dimensions", name="embedding_dimensions"),
        schema="memory",
    )


def downgrade() -> None:
    op.drop_table("memory_search_embeddings", schema="memory")
