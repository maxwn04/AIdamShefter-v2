from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
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
            "generation_id", "path", name="uq_artifacts_generation_path"
        ),
        UniqueConstraint(
            "id", "generation_id", name="uq_artifacts_id_generation"
        ),
        CheckConstraint(
            "(finalized_version_id IS NULL) = (finalized_at IS NULL)",
            name="finalization_shape",
        ),
        ForeignKeyConstraint(
            ["finalized_version_id", "id", "generation_id"],
            [
                "reporting.artifact_versions.id",
                "reporting.artifact_versions.artifact_id",
                "reporting.artifact_versions.generation_id",
            ],
            name="fk_artifacts_finalized_version_same_artifact",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index("ix_artifacts_generation_path", "generation_id", "path"),
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
    path: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    finalized_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
            "id",
            "artifact_id",
            "generation_id",
            name="uq_artifact_versions_id_artifact_generation",
        ),
        UniqueConstraint(
            "artifact_id",
            "revision_number",
            name="uq_artifact_versions_artifact_revision",
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
