"""Rebuildable vectors, separate from immutable canonical memory."""

from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.dialects.postgresql.base import ischema_names
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


# The maintained adapter registers "vector". With the application's hardened
# pg_catalog search path, PostgreSQL reflects this type as "public.vector".
# Register that qualified spelling too so Alembic compares the real type.
ischema_names["public.vector"] = Vector


class MemorySearchEmbedding(Base):
    __tablename__ = "memory_search_embeddings"
    __table_args__ = (
        CheckConstraint("dimensions > 0", name="positive_dimensions"),
        CheckConstraint("public.vector_dims(embedding) = dimensions", name="embedding_dimensions"),
        {"schema": "memory"},
    )

    version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("memory.memory_versions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(Text, primary_key=True)
    model: Mapped[str] = mapped_column(Text, primary_key=True)
    dimensions: Mapped[int] = mapped_column(Integer, primary_key=True)
    text_format_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_builder_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
