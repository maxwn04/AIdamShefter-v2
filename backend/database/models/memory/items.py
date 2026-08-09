from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Computed,
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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class MemoryItem(Base):
    __tablename__ = "memory_items"
    __table_args__ = (
        UniqueConstraint(
            "id", "competition_id", name="uq_memory_items_id_competition"
        ),
        Index("ix_memory_items_competition_kind", "competition_id", "kind"),
        Index("ix_memory_items_competition_agent_key", "competition_id", "agent_key"),
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
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    agent_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MemoryVersion(Base):
    __tablename__ = "memory_versions"
    __table_args__ = (
        UniqueConstraint(
            "item_id", "revision_number", name="uq_memory_versions_item_revision"
        ),
        UniqueConstraint(
            "id", "competition_id", name="uq_memory_versions_id_competition"
        ),
        ForeignKeyConstraint(
            ["item_id", "competition_id"],
            ["memory.memory_items.id", "memory.memory_items.competition_id"],
            name="fk_memory_versions_item_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["introduced_revision_id", "competition_id"],
            ["memory.memory_revisions.id", "memory.memory_revisions.competition_id"],
            name="fk_memory_versions_introduced_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["retired_revision_id", "competition_id"],
            ["memory.memory_revisions.id", "memory.memory_revisions.competition_id"],
            name="fk_memory_versions_retired_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["competition_season_id", "competition_id"],
            [
                "core.competition_seasons.id",
                "core.competition_seasons.competition_id",
            ],
            name="fk_memory_versions_season_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["creating_generation_id", "competition_id"],
            ["reporting.generations.id", "reporting.generations.competition_id"],
            name="fk_memory_versions_generation_same_competition",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["creating_tool_call_id", "creating_generation_id"],
            ["reporting.tool_calls.id", "reporting.tool_calls.generation_id"],
            name="fk_memory_versions_tool_call_same_generation",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index("ix_memory_versions_item_revision", "item_id", "revision_number"),
        Index("ix_memory_versions_introduced_revision", "introduced_revision_id"),
        Index("ix_memory_versions_retired_revision", "retired_revision_id"),
        Index(
            "ix_memory_versions_creating_generation",
            "creating_generation_id",
            "competition_id",
        ),
        Index(
            "ix_memory_versions_creating_tool_call",
            "creating_tool_call_id",
            "creating_generation_id",
        ),
        Index(
            "ix_memory_versions_competition_season_week",
            "competition_id",
            "competition_season_id",
            "week",
        ),
        Index(
            "ix_memory_versions_season_competition",
            "competition_season_id",
            "competition_id",
        ),
        {"schema": "memory"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    competition_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    revision_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    content_schema_version: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    introduced_revision_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    retired_revision_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    competition_season_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    week: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    creating_generation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    creating_tool_call_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StorylineVersion(Base):
    __tablename__ = "storyline_versions"
    __table_args__ = (
        {"schema": "memory"},
    )

    version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("memory.memory_versions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    arc_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    salience: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    subjects: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    evidence: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    related_storylines: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    callback_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class FactVersion(Base):
    __tablename__ = "fact_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "competition_id"],
            ["memory.memory_versions.id", "memory.memory_versions.competition_id"],
            name="fk_fact_versions_version_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["primary_tool_call_id", "primary_tool_call_generation_id"],
            ["reporting.tool_calls.id", "reporting.tool_calls.generation_id"],
            name="fk_fact_versions_tool_call_same_generation",
            ondelete="RESTRICT",
            match="FULL",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["primary_tool_call_generation_id", "competition_id"],
            ["reporting.generations.id", "reporting.generations.competition_id"],
            name="fk_fact_versions_tool_generation_same_competition",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index(
            "ix_fact_versions_primary_tool_call",
            "primary_tool_call_id",
            "primary_tool_call_generation_id",
        ),
        Index(
            "ix_fact_versions_tool_generation_competition",
            "primary_tool_call_generation_id",
            "competition_id",
        ),
        Index("ix_fact_versions_primary_api_request", "primary_api_request_id"),
        {"schema": "memory"},
    )

    version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )
    competition_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    structured_numbers: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[str] = mapped_column(Text, nullable=False)
    subjects: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    originating_event_version_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)),
        nullable=False,
        default=list,
        server_default=text("'{}'::uuid[]"),
    )
    primary_tool_call_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    primary_tool_call_generation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    primary_api_request_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sleeper.api_requests.id", ondelete="RESTRICT"),
        nullable=True,
    )
    additional_source_hints: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)


class EventVersion(Base):
    __tablename__ = "event_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "competition_id"],
            ["memory.memory_versions.id", "memory.memory_versions.competition_id"],
            name="fk_event_versions_version_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["primary_tool_call_id", "primary_tool_call_generation_id"],
            ["reporting.tool_calls.id", "reporting.tool_calls.generation_id"],
            name="fk_event_versions_tool_call_same_generation",
            ondelete="RESTRICT",
            match="FULL",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["primary_tool_call_generation_id", "competition_id"],
            ["reporting.generations.id", "reporting.generations.competition_id"],
            name="fk_event_versions_tool_generation_same_competition",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index(
            "ix_event_versions_primary_tool_call",
            "primary_tool_call_id",
            "primary_tool_call_generation_id",
        ),
        Index(
            "ix_event_versions_tool_generation_competition",
            "primary_tool_call_generation_id",
            "competition_id",
        ),
        Index("ix_event_versions_primary_api_request", "primary_api_request_id"),
        {"schema": "memory"},
    )

    version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )
    competition_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    salience: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    confidence: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    additional_source_hints: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    primary_tool_call_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    primary_tool_call_generation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    primary_api_request_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sleeper.api_requests.id", ondelete="RESTRICT"),
        nullable=True,
    )


class TriggerVersion(Base):
    __tablename__ = "trigger_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "competition_id"],
            ["memory.memory_versions.id", "memory.memory_versions.competition_id"],
            name="fk_trigger_versions_version_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["target_competition_season_id", "competition_id"],
            [
                "core.competition_seasons.id",
                "core.competition_seasons.competition_id",
            ],
            name="fk_trigger_versions_target_same_competition",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_trigger_versions_target_season_competition",
            "target_competition_season_id",
            "competition_id",
        ),
        {"schema": "memory"},
    )

    version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )
    competition_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    trigger_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    fire_policy: Mapped[str] = mapped_column(Text, nullable=False)
    target_competition_season_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    target_storyline_item_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    origin_event_item_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    target_week: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    target_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    condition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


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
