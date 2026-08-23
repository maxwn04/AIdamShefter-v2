from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class Generation(Base):
    __tablename__ = "generations"
    __table_args__ = (
        UniqueConstraint(
            "id", "competition_id", name="uq_generations_id_competition"
        ),
        UniqueConstraint(
            "id",
            "evaluation_workspace_id",
            "competition_id",
            name="uq_generations_id_workspace_competition",
        ),
        UniqueConstraint(
            "evaluation_workspace_id",
            "workspace_sequence_number",
            name="uq_generations_workspace_sequence",
        ),
        ForeignKeyConstraint(
            ["competition_season_id", "competition_id"],
            [
                "core.competition_seasons.id",
                "core.competition_seasons.competition_id",
            ],
            name="fk_generations_season_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["data_snapshot_id", "competition_id"],
            ["sleeper.data_snapshots.id", "sleeper.data_snapshots.competition_id"],
            name="fk_generations_snapshot_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["data_snapshot_id", "competition_season_id"],
            [
                "sleeper.data_snapshots.id",
                "sleeper.data_snapshots.primary_competition_season_id",
            ],
            name="fk_generations_snapshot_same_season",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["input_memory_revision_id", "competition_id"],
            ["memory.memory_revisions.id", "memory.memory_revisions.competition_id"],
            name="fk_generations_memory_revision_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["evaluation_workspace_id", "competition_id"],
            [
                "reporting.evaluation_workspaces.id",
                "reporting.evaluation_workspaces.competition_id",
            ],
            name="fk_generations_workspace_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["rerun_of_generation_id", "competition_id"],
            ["reporting.generations.id", "reporting.generations.competition_id"],
            name="fk_generations_rerun_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["input_memory_artifact_version_id", "input_memory_artifact_generation_id"],
            ["reporting.artifact_versions.id", "reporting.artifact_versions.generation_id"],
            name="fk_generations_input_artifact_same_generation",
            ondelete="RESTRICT",
            match="FULL",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["submitted_artifact_version_id", "id"],
            [
                "reporting.artifacts.finalized_version_id",
                "reporting.artifacts.generation_id",
            ],
            name="fk_generations_submitted_artifact_finalized",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            [
                "input_memory_artifact_generation_id",
                "evaluation_workspace_id",
                "competition_id",
            ],
            [
                "reporting.generations.id",
                "reporting.generations.evaluation_workspace_id",
                "reporting.generations.competition_id",
            ],
            name="fk_generations_input_artifact_workspace_scope",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        CheckConstraint(
            "(evaluation_workspace_id IS NULL AND workspace_sequence_number IS NULL) OR "
            "(evaluation_workspace_id IS NOT NULL AND workspace_sequence_number IS NOT NULL)",
            name="workspace_shape",
        ),
        CheckConstraint(
            "num_nonnulls(input_memory_revision_id, input_memory_artifact_version_id) <= 1 "
            "AND ((input_memory_artifact_version_id IS NULL AND "
            "input_memory_artifact_generation_id IS NULL) OR "
            "(input_memory_artifact_version_id IS NOT NULL AND "
            "input_memory_artifact_generation_id IS NOT NULL AND "
            "evaluation_workspace_id IS NOT NULL))",
            name="unambiguous_memory_input",
        ),
        CheckConstraint(
            "submitted_artifact_version_id IS NULL OR status = 'succeeded'",
            name="submitted_artifact_shape",
        ),
        Index("ix_generations_competition_created", "competition_id", text("created_at DESC")),
        Index("ix_generations_status_progress", "status", "progress_updated_at"),
        Index("ix_generations_competition_season", "competition_season_id"),
        Index(
            "ix_generations_data_snapshot",
            "data_snapshot_id",
            "competition_season_id",
        ),
        Index("ix_generations_memory_revision", "input_memory_revision_id"),
        Index(
            "ix_generations_input_artifact",
            "input_memory_artifact_version_id",
            "input_memory_artifact_generation_id",
        ),
        Index(
            "ix_generations_input_artifact_workspace",
            "input_memory_artifact_generation_id",
            "evaluation_workspace_id",
            "competition_id",
        ),
        Index(
            "ix_generations_workspace_sequence",
            "evaluation_workspace_id",
            "workspace_sequence_number",
        ),
        Index("ix_generations_requested_model", "requested_primary_model"),
        Index(
            "ix_generations_competition_submitted_completed",
            "competition_id",
            text("completed_at DESC"),
            text("id DESC"),
            postgresql_where=text(
                "status = 'succeeded' "
                "AND submitted_artifact_version_id IS NOT NULL"
            ),
        ),
        {"schema": "reporting"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    competition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("core.competitions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    competition_season_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    data_snapshot_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    input_memory_revision_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    input_memory_artifact_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    input_memory_artifact_generation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    evaluation_workspace_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    workspace_sequence_number: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    rerun_of_generation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    submitted_artifact_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    week_start: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    week_end: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    domain_cutoff_week: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    domain_cutoff_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    knowledge_cutoff_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    requested_primary_model: Mapped[str] = mapped_column(Text, nullable=False)
    settings_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    input_manifest_jsonb: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    manifest_schema_version: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True
    )
    manifest_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_turn: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    current_stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EvaluationWorkspace(Base):
    __tablename__ = "evaluation_workspaces"
    __table_args__ = (
        UniqueConstraint(
            "id", "competition_id", name="uq_evaluation_workspaces_id_competition"
        ),
        ForeignKeyConstraint(
            ["base_memory_revision_id", "competition_id"],
            ["memory.memory_revisions.id", "memory.memory_revisions.competition_id"],
            name="fk_evaluation_workspaces_base_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["promoted_memory_revision_id", "competition_id"],
            ["memory.memory_revisions.id", "memory.memory_revisions.competition_id"],
            name="fk_evaluation_workspaces_promoted_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "current_memory_artifact_version_id",
                "current_memory_artifact_generation_id",
            ],
            ["reporting.artifact_versions.id", "reporting.artifact_versions.generation_id"],
            name="fk_evaluation_workspaces_current_artifact_same_generation",
            ondelete="RESTRICT",
            match="FULL",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["current_memory_artifact_generation_id", "id", "competition_id"],
            [
                "reporting.generations.id",
                "reporting.generations.evaluation_workspace_id",
                "reporting.generations.competition_id",
            ],
            name="fk_evaluation_workspaces_current_artifact_workspace_scope",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index(
            "uq_evaluation_workspaces_one_active",
            "competition_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "ix_evaluation_workspaces_competition_status",
            "competition_id",
            "status",
        ),
        Index("ix_evaluation_workspaces_base_revision", "base_memory_revision_id"),
        Index(
            "ix_evaluation_workspaces_current_artifact",
            "current_memory_artifact_version_id",
            "current_memory_artifact_generation_id",
        ),
        Index(
            "ix_evaluation_workspaces_current_artifact_workspace",
            "current_memory_artifact_generation_id",
            "id",
            "competition_id",
        ),
        {"schema": "reporting"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    competition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("core.competitions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    base_memory_revision_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    current_memory_artifact_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    current_memory_artifact_generation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    promoted_memory_revision_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
