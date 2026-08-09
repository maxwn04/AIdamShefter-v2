from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class MemoryRevision(Base):
    __tablename__ = "memory_revisions"
    __table_args__ = (
        UniqueConstraint(
            "competition_id",
            "sequence_number",
            name="uq_memory_revisions_competition_sequence",
        ),
        UniqueConstraint(
            "id",
            "competition_id",
            name="uq_memory_revisions_id_competition",
        ),
        UniqueConstraint(
            "producing_generation_id",
            name="uq_memory_revisions_producing_generation",
        ),
        ForeignKeyConstraint(
            ["previous_revision_id", "competition_id"],
            ["memory.memory_revisions.id", "memory.memory_revisions.competition_id"],
            name="fk_memory_revisions_previous_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["competition_season_id", "competition_id"],
            [
                "core.competition_seasons.id",
                "core.competition_seasons.competition_id",
            ],
            name="fk_memory_revisions_season_same_competition",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_memory_revisions_competition_sequence_desc",
            "competition_id",
            text("sequence_number DESC"),
        ),
        Index(
            "ix_memory_revisions_previous_competition",
            "previous_revision_id",
            "competition_id",
        ),
        Index(
            "ix_memory_revisions_season_competition",
            "competition_season_id",
            "competition_id",
        ),
        Index(
            "ix_memory_revisions_producing_generation",
            "producing_generation_id",
        ),
        {"schema": "memory"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    competition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("core.competitions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    previous_revision_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    # Cross-namespace FK to reporting.generations is added in revision 0006.
    producing_generation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    competition_season_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    week: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    knowledge_cutoff_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    state_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CurrentRevision(Base):
    __tablename__ = "current_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["current_revision_id", "competition_id"],
            ["memory.memory_revisions.id", "memory.memory_revisions.competition_id"],
            name="fk_current_revisions_revision_same_competition",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_current_revisions_revision_competition",
            "current_revision_id",
            "competition_id",
        ),
        {"schema": "memory"},
    )

    competition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("core.competitions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    current_revision_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    lock_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
