from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint(
            "generation_id", "kind", "name", name="uq_artifacts_generation_kind_name"
        ),
        UniqueConstraint(
            "id", "generation_id", name="uq_artifacts_id_generation"
        ),
        Index("ix_artifacts_generation_kind", "generation_id", "kind"),
        {"schema": "reporting"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    generation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("reporting.generations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"
    __table_args__ = (
        UniqueConstraint(
            "id", "generation_id", name="uq_artifact_versions_id_generation"
        ),
        UniqueConstraint(
            "artifact_id",
            "revision_number",
            name="uq_artifact_versions_artifact_revision",
        ),
        Index(
            "uq_artifact_versions_one_final",
            "artifact_id",
            unique=True,
            postgresql_where=text("status = 'final'"),
        ),
        ForeignKeyConstraint(
            ["artifact_id", "generation_id"],
            ["reporting.artifacts.id", "reporting.artifacts.generation_id"],
            name="fk_artifact_versions_artifact_same_generation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_ai_call_id", "generation_id"],
            ["reporting.ai_calls.id", "reporting.ai_calls.generation_id"],
            name="fk_artifact_versions_ai_call_same_generation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_tool_call_id", "generation_id"],
            ["reporting.tool_calls.id", "reporting.tool_calls.generation_id"],
            name="fk_artifact_versions_tool_call_same_generation",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_artifact_versions_artifact_revision_desc",
            "artifact_id",
            text("revision_number DESC"),
        ),
        Index(
            "ix_artifact_versions_final",
            "artifact_id",
            postgresql_where=text("status = 'final'"),
        ),
        {"schema": "reporting"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    generation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    revision_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_ai_call_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    source_tool_call_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
