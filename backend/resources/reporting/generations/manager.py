"""Competition-scoped lifecycle manager for durable generations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database.models.core import CompetitionSeason
from backend.database.models.memory import MemoryRevision
from backend.database.models.reporting import EvaluationWorkspace
from backend.database.models.reporting import Generation as StoredGeneration
from backend.database.models.sleeper import DataSnapshot
from backend.database.sessions import (
    SessionFactory,
    read_only_session,
    transaction_session,
)
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.reporting.generations.errors import (
    GenerationConcurrencyConflict,
    GenerationLifecycleConflict,
    GenerationResourceNotFound,
)
from backend.resources.reporting.generations.objects import (
    CancelGeneration,
    CreateGeneration,
    FailGeneration,
    Generation,
    GenerationDetail,
    GenerationPage,
    GenerationQuery,
    GenerationStatus,
    GenerationSummary,
    StartGeneration,
    UpdateGenerationProgress,
)


_TERMINAL_STATUSES = {
    GenerationStatus.SUCCEEDED.value,
    GenerationStatus.FAILED.value,
    GenerationStatus.CANCELLED.value,
}


class GenerationManager:
    """Own pending creation, input pinning, progress, and terminal transitions."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id

    @property
    def competition_id(self) -> UUID:
        return self._competition_id

    def create_pending(self, command: CreateGeneration) -> Generation:
        try:
            with transaction_session(self._session_factory) as session:
                self._require_season(session, command.competition_season_id)
                if command.rerun_of_generation_id is not None:
                    original = self._load(session, command.rerun_of_generation_id)
                    if original.status not in _TERMINAL_STATUSES:
                        raise _lifecycle(
                            original,
                            "reruns require a terminal source generation",
                            _TERMINAL_STATUSES,
                        )
                if command.evaluation_workspace_id is not None:
                    workspace = self._load_workspace(
                        session, command.evaluation_workspace_id
                    )
                    if workspace.status != "active":
                        raise GenerationLifecycleConflict(
                            command.generation_id,
                            "new generations require an active evaluation workspace",
                            expected_statuses=("active",),
                            actual_status=workspace.status,
                        )

                stored = StoredGeneration(
                    id=command.generation_id,
                    competition_id=self._competition_id,
                    competition_season_id=command.competition_season_id,
                    evaluation_workspace_id=command.evaluation_workspace_id,
                    workspace_sequence_number=command.workspace_sequence_number,
                    rerun_of_generation_id=command.rerun_of_generation_id,
                    kind=command.kind.value,
                    status=GenerationStatus.PENDING.value,
                    request_text=command.request_text,
                    week_start=command.week_start,
                    week_end=command.week_end,
                    requested_primary_model=command.requested_primary_model,
                    settings_jsonb=command.settings,
                    current_turn=0,
                )
                session.add(stored)
                session.flush()
                return _decode(stored)
        except IntegrityError:
            raise GenerationConcurrencyConflict(
                "generation identity or workspace sequence is already allocated"
            ) from None

    def start(self, command: StartGeneration) -> Generation:
        with transaction_session(self._session_factory) as session:
            stored = self._load(session, command.generation_id, lock=True)
            self._require_status(stored, GenerationStatus.PENDING)
            snapshot = session.scalar(
                sa.select(DataSnapshot).where(
                    DataSnapshot.id == command.data_snapshot_id,
                    DataSnapshot.competition_id == self._competition_id,
                    DataSnapshot.primary_competition_season_id
                    == stored.competition_season_id,
                )
            )
            if snapshot is None:
                raise GenerationResourceNotFound(
                    "data_snapshot", command.data_snapshot_id
                )
            if snapshot.status != "ready":
                raise GenerationLifecycleConflict(
                    stored.id,
                    "generation inputs require a ready data snapshot",
                    expected_statuses=("ready",),
                    actual_status=snapshot.status,
                )
            self._validate_memory_input(session, stored, command)

            now = datetime.now(UTC)
            stored.data_snapshot_id = snapshot.id
            stored.input_memory_revision_id = command.input_memory_revision_id
            stored.input_memory_artifact_version_id = (
                command.input_memory_artifact_version_id
            )
            stored.input_memory_artifact_generation_id = (
                command.input_memory_artifact_generation_id
            )
            stored.domain_cutoff_week = snapshot.domain_cutoff_week
            stored.domain_cutoff_at = snapshot.domain_cutoff_at
            stored.knowledge_cutoff_at = command.knowledge_cutoff_at
            stored.input_manifest_jsonb = command.input_manifest
            stored.manifest_schema_version = command.manifest_schema_version
            stored.manifest_hash = command.manifest_hash
            stored.status = GenerationStatus.RUNNING.value
            stored.current_stage = command.initial_stage
            stored.progress_updated_at = now
            stored.started_at = now
            session.flush()
            return _decode(stored)

    def update_progress(self, command: UpdateGenerationProgress) -> Generation:
        with transaction_session(self._session_factory) as session:
            stored = self._load(session, command.generation_id, lock=True)
            self._require_status(stored, GenerationStatus.RUNNING)
            if command.current_turn < stored.current_turn:
                raise GenerationLifecycleConflict(
                    stored.id,
                    "generation progress cannot move to an earlier turn",
                    actual_status=stored.status,
                )
            stored.current_turn = command.current_turn
            stored.current_stage = command.current_stage
            stored.progress_updated_at = datetime.now(UTC)
            session.flush()
            return _decode(stored)

    def fail(self, command: FailGeneration) -> Generation:
        with transaction_session(self._session_factory) as session:
            stored = self._load(session, command.generation_id, lock=True)
            self._require_active(stored)
            now = datetime.now(UTC)
            stored.status = GenerationStatus.FAILED.value
            stored.current_stage = "failed"
            stored.failure_category = command.category
            stored.failure_summary = command.summary
            stored.progress_updated_at = now
            stored.completed_at = now
            session.flush()
            return _decode(stored)

    def cancel(self, command: CancelGeneration) -> Generation:
        with transaction_session(self._session_factory) as session:
            stored = self._load(session, command.generation_id, lock=True)
            self._require_active(stored)
            now = datetime.now(UTC)
            stored.status = GenerationStatus.CANCELLED.value
            stored.current_stage = "cancelled"
            stored.failure_category = "cancelled"
            stored.failure_summary = command.summary or "Generation was cancelled"
            stored.progress_updated_at = now
            stored.completed_at = now
            session.flush()
            return _decode(stored)

    def get(self, generation_id: UUID) -> GenerationDetail:
        with read_only_session(self._session_factory) as session:
            return _decode_detail(self._load(session, generation_id))

    def list(self, query: GenerationQuery) -> GenerationPage:
        with read_only_session(self._session_factory) as session:
            conditions: list[sa.ColumnElement[bool]] = [
                StoredGeneration.competition_id == self._competition_id
            ]
            if query.competition_season_id is not None:
                conditions.append(
                    StoredGeneration.competition_season_id
                    == query.competition_season_id
                )
            if query.kind is not None:
                conditions.append(StoredGeneration.kind == query.kind.value)
            if query.status is not None:
                conditions.append(StoredGeneration.status == query.status.value)
            if query.rerun_of_generation_id is not None:
                conditions.append(
                    StoredGeneration.rerun_of_generation_id
                    == query.rerun_of_generation_id
                )
            if query.evaluation_workspace_id is not None:
                conditions.append(
                    StoredGeneration.evaluation_workspace_id
                    == query.evaluation_workspace_id
                )
            total = cast(
                int,
                session.scalar(
                    sa.select(sa.func.count())
                    .select_from(StoredGeneration)
                    .where(*conditions)
                ),
            )
            rows = session.scalars(
                sa.select(StoredGeneration)
                .where(*conditions)
                .order_by(
                    StoredGeneration.created_at.desc(),
                    StoredGeneration.id.desc(),
                )
                .limit(query.limit)
                .offset(query.offset)
            ).all()
            return GenerationPage(
                items=tuple(_decode_summary(row) for row in rows),
                total=total,
                limit=query.limit,
                offset=query.offset,
            )

    def _validate_memory_input(
        self,
        session: Session,
        generation: StoredGeneration,
        command: StartGeneration,
    ) -> None:
        if command.input_memory_revision_id is not None:
            revision = session.scalar(
                sa.select(MemoryRevision.id).where(
                    MemoryRevision.id == command.input_memory_revision_id,
                    MemoryRevision.competition_id == self._competition_id,
                )
            )
            if revision is None:
                raise GenerationResourceNotFound(
                    "memory_revision", command.input_memory_revision_id
                )
            return

        workspace_id = generation.evaluation_workspace_id
        if workspace_id is None:
            raise GenerationLifecycleConflict(
                generation.id,
                "workspace memory input requires workspace generation membership",
            )
        workspace = self._load_workspace(session, workspace_id, lock=True)
        if workspace.status != "active":
            raise GenerationLifecycleConflict(
                generation.id,
                "workspace memory input requires an active workspace",
                expected_statuses=("active",),
                actual_status=workspace.status,
            )
        if (
            workspace.current_memory_artifact_version_id
            != command.input_memory_artifact_version_id
            or workspace.current_memory_artifact_generation_id
            != command.input_memory_artifact_generation_id
        ):
            raise GenerationConcurrencyConflict(
                "workspace memory input is not the current workspace artifact"
            )
        source = session.scalar(
            sa.select(StoredGeneration).where(
                StoredGeneration.id == command.input_memory_artifact_generation_id,
                StoredGeneration.competition_id == self._competition_id,
                StoredGeneration.evaluation_workspace_id == workspace.id,
            )
        )
        if source is None:
            raise GenerationResourceNotFound(
                "generation", cast(UUID, command.input_memory_artifact_generation_id)
            )
        if source.status != GenerationStatus.SUCCEEDED.value:
            raise GenerationLifecycleConflict(
                generation.id,
                "workspace memory input must come from a succeeded generation",
                expected_statuses=(GenerationStatus.SUCCEEDED.value,),
                actual_status=source.status,
            )

    def _load(
        self,
        session: Session,
        generation_id: UUID,
        *,
        lock: bool = False,
    ) -> StoredGeneration:
        statement = sa.select(StoredGeneration).where(
            StoredGeneration.id == generation_id,
            StoredGeneration.competition_id == self._competition_id,
        )
        if lock:
            statement = statement.with_for_update()
        stored = session.scalar(statement)
        if stored is None:
            raise GenerationResourceNotFound("generation", generation_id)
        return stored

    def _load_workspace(
        self,
        session: Session,
        workspace_id: UUID,
        *,
        lock: bool = False,
    ) -> EvaluationWorkspace:
        statement = sa.select(EvaluationWorkspace).where(
            EvaluationWorkspace.id == workspace_id,
            EvaluationWorkspace.competition_id == self._competition_id,
        )
        if lock:
            statement = statement.with_for_update()
        workspace = session.scalar(statement)
        if workspace is None:
            raise GenerationResourceNotFound("evaluation_workspace", workspace_id)
        return workspace

    def _require_season(self, session: Session, season_id: UUID) -> None:
        season = session.scalar(
            sa.select(CompetitionSeason.id).where(
                CompetitionSeason.id == season_id,
                CompetitionSeason.competition_id == self._competition_id,
            )
        )
        if season is None:
            raise GenerationResourceNotFound("competition_season", season_id)

    @staticmethod
    def _require_status(
        stored: StoredGeneration,
        expected: GenerationStatus,
    ) -> None:
        if stored.status != expected.value:
            raise _lifecycle(
                stored,
                f"generation must be {expected.value} for this operation",
                (expected.value,),
            )

    @staticmethod
    def _require_active(stored: StoredGeneration) -> None:
        active = (GenerationStatus.PENDING.value, GenerationStatus.RUNNING.value)
        if stored.status not in active:
            raise _lifecycle(
                stored,
                "only a pending or running generation can become terminal",
                active,
            )


def _lifecycle(
    stored: StoredGeneration,
    message: str,
    expected_statuses: set[str] | tuple[str, ...],
) -> GenerationLifecycleConflict:
    return GenerationLifecycleConflict(
        stored.id,
        message,
        expected_statuses=expected_statuses,
        actual_status=stored.status,
    )


def _generation_values(stored: StoredGeneration) -> dict[str, object]:
    return {
        "id": stored.id,
        "competition_id": stored.competition_id,
        "competition_season_id": stored.competition_season_id,
        "data_snapshot_id": stored.data_snapshot_id,
        "input_memory_revision_id": stored.input_memory_revision_id,
        "input_memory_artifact_version_id": stored.input_memory_artifact_version_id,
        "input_memory_artifact_generation_id": (
            stored.input_memory_artifact_generation_id
        ),
        "evaluation_workspace_id": stored.evaluation_workspace_id,
        "workspace_sequence_number": stored.workspace_sequence_number,
        "rerun_of_generation_id": stored.rerun_of_generation_id,
        "kind": stored.kind,
        "status": stored.status,
        "request_text": stored.request_text,
        "week_start": stored.week_start,
        "week_end": stored.week_end,
        "domain_cutoff_week": stored.domain_cutoff_week,
        "domain_cutoff_at": stored.domain_cutoff_at,
        "knowledge_cutoff_at": stored.knowledge_cutoff_at,
        "requested_primary_model": stored.requested_primary_model,
        "settings": stored.settings_jsonb,
        "input_manifest": stored.input_manifest_jsonb,
        "manifest_schema_version": stored.manifest_schema_version,
        "manifest_hash": stored.manifest_hash,
        "current_turn": stored.current_turn,
        "current_stage": stored.current_stage,
        "progress_updated_at": stored.progress_updated_at,
        "failure_category": stored.failure_category,
        "failure_summary": stored.failure_summary,
        "created_at": stored.created_at,
        "started_at": stored.started_at,
        "completed_at": stored.completed_at,
    }


def _decode(stored: StoredGeneration) -> Generation:
    return Generation.model_validate(_generation_values(stored))


def _decode_detail(stored: StoredGeneration) -> GenerationDetail:
    return GenerationDetail.model_validate(_generation_values(stored))


def _decode_summary(stored: StoredGeneration) -> GenerationSummary:
    return GenerationSummary(
        id=stored.id,
        competition_id=stored.competition_id,
        competition_season_id=stored.competition_season_id,
        evaluation_workspace_id=stored.evaluation_workspace_id,
        workspace_sequence_number=stored.workspace_sequence_number,
        rerun_of_generation_id=stored.rerun_of_generation_id,
        kind=stored.kind,
        status=stored.status,
        request_text=stored.request_text,
        week_start=stored.week_start,
        week_end=stored.week_end,
        requested_primary_model=stored.requested_primary_model,
        current_turn=stored.current_turn,
        current_stage=stored.current_stage,
        progress_updated_at=stored.progress_updated_at,
        failure_category=stored.failure_category,
        failure_summary=stored.failure_summary,
        created_at=stored.created_at,
        started_at=stored.started_at,
        completed_at=stored.completed_at,
    )


__all__ = ["GenerationManager"]
