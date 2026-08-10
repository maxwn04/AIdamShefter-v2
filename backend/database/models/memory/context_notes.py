from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class ContextNote(Base):
    __tablename__ = "context_notes"
    __table_args__ = (
        UniqueConstraint(
            "item_id", "competition_id", name="uq_context_notes_item_competition"
        ),
        ForeignKeyConstraint(
            ["item_id", "competition_id"],
            ["memory.memory_items.id", "memory.memory_items.competition_id"],
            name="fk_context_notes_item_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["competition_season_id", "competition_id"],
            [
                "core.competition_seasons.id",
                "core.competition_seasons.competition_id",
            ],
            name="fk_context_notes_season_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["franchise_id", "competition_id"],
            ["core.franchises.id", "core.franchises.competition_id"],
            name="fk_context_notes_franchise_same_competition",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(scope = 'competition' AND competition_season_id IS NULL AND "
            "franchise_id IS NULL) OR "
            "(scope = 'competition_season' AND competition_season_id IS NOT NULL "
            "AND franchise_id IS NULL) OR "
            "(scope = 'franchise' AND competition_season_id IS NULL AND "
            "franchise_id IS NOT NULL)",
            name="scope_shape",
        ),
        Index(
            "uq_context_notes_competition_key",
            "competition_id",
            "note_key",
            unique=True,
            postgresql_where=text("scope = 'competition'"),
        ),
        Index(
            "uq_context_notes_season_key",
            "competition_season_id",
            "note_key",
            unique=True,
            postgresql_where=text("scope = 'competition_season'"),
        ),
        Index(
            "uq_context_notes_franchise_key",
            "franchise_id",
            "note_key",
            unique=True,
            postgresql_where=text("scope = 'franchise'"),
        ),
        {"schema": "memory"},
    )

    item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    competition_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    competition_season_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    franchise_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    note_key: Mapped[str] = mapped_column(Text, nullable=False)


class ContextNoteVersion(Base):
    __tablename__ = "context_note_versions"
    __table_args__ = ({"schema": "memory"},)

    version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("memory.memory_versions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    narrative_text: Mapped[str] = mapped_column(Text, nullable=False)
    outlook: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
