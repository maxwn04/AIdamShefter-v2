from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class MemorySearchDocument(Base):
    __tablename__ = "memory_search_documents"
    __table_args__ = (
        Index(
            "ix_memory_search_documents_competition_kind_status",
            "competition_id",
            "kind",
            "status",
        ),
        Index("ix_memory_search_documents_item", "item_id"),
        Index(
            "ix_memory_search_documents_entity_keys",
            "entity_keys",
            postgresql_using="gin",
        ),
        Index(
            "ix_memory_search_documents_evidence_versions",
            "evidence_version_ids",
            postgresql_using="gin",
        ),
        Index(
            "ix_memory_search_documents_related_items",
            "related_item_ids",
            postgresql_using="gin",
        ),
        Index(
            "ix_memory_search_documents_tags",
            "tags",
            postgresql_using="gin",
        ),
        Index(
            "ix_memory_search_documents_search_vector",
            "search_vector",
            postgresql_using="gin",
        ),
        {"schema": "memory"},
    )

    version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("memory.memory_versions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    competition_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    salience: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    competition_season_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    week: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    entity_keys: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'::text[]"),
    )
    evidence_version_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)),
        nullable=False,
        default=list,
        server_default=text("'{}'::uuid[]"),
    )
    related_item_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)),
        nullable=False,
        default=list,
        server_default=text("'{}'::uuid[]"),
    )
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'::text[]"),
    )
    document_text: Mapped[str] = mapped_column(Text, nullable=False)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', document_text)", persisted=True),
        nullable=False,
    )
    builder_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
