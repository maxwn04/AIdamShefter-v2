"""Atomic selected-artifact, canonical-memory, and generation finalization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from backend.database.models.reporting import Generation as StoredGeneration
from backend.database.sessions import SessionFactory, transaction_session
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.memory.revisions.manager import (
    _commit_canonical_bundle_in_session,
)
from backend.resources.memory.revisions.writers import lock_current_revision
from backend.resources.reporting.artifacts import FinalizeArtifact
from backend.resources.reporting.artifacts.manager import (
    _finalize_artifact_in_session,
    _resolve_exact_artifact_version_in_session,
)
from backend.resources.reporting.generations import (
    Generation,
    GenerationKind,
    GenerationLifecycleConflict,
    GenerationStatus,
    SucceedGeneration,
)
from backend.resources.reporting.generations.manager import (
    _load_generation_in_session,
    _succeed_generation_in_session,
)
from backend.services.memory import MemoryMutationBundle, MemoryMutationResult
from backend.services.memory.mutation_service import prepare_canonical_bundle
from backend.services.reporter import ReporterOutput


class GenerationFinalizationError(RuntimeError):
    """Stable workflow failure raised before an atomic success commit."""


@dataclass(frozen=True, slots=True)
class GenerationFinalizationResult:
    generation: Generation
    memory_result: MemoryMutationResult | None


class GenerationFinalizer:
    """Own the one PostgreSQL transaction that makes a run successful."""

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

    def finalize(
        self,
        generation_id: UUID,
        output: ReporterOutput,
        memory_bundle: MemoryMutationBundle,
    ) -> GenerationFinalizationResult:
        selected = output.submitted_artifact
        if selected is None:
            raise GenerationFinalizationError(
                "reporter output must select one submitted artifact"
            )
        if not selected.content.strip():
            raise GenerationFinalizationError(
                "reporter output cannot submit an empty artifact"
            )

        with transaction_session(self._session_factory) as session:
            stored = _load_generation_in_session(
                session,
                self._competition_id,
                generation_id,
                lock=True,
            )
            if stored.status != GenerationStatus.RUNNING.value:
                raise GenerationLifecycleConflict(
                    stored.id,
                    "generation must be running for finalization",
                    expected_statuses=(GenerationStatus.RUNNING.value,),
                    actual_status=stored.status,
                )
            self._validate_memory_bundle(stored, memory_bundle)
            artifact, version = _resolve_exact_artifact_version_in_session(
                session,
                self._competition_id,
                generation_id=generation_id,
                path=selected.path,
                media_type=selected.media_type,
                revision_number=selected.revision,
                content=selected.content,
                content_hash=selected.content_hash,
            )

            memory_result: MemoryMutationResult | None = None
            if stored.kind == GenerationKind.LIVE.value:
                prepared = prepare_canonical_bundle(memory_bundle)
                if (
                    not prepared.writes
                    and stored.settings_jsonb.get("prepared_execution") is not None
                ):
                    # Quiet simulation weeks still require the promised input head
                    # to remain current until article success commits atomically.
                    lock_current_revision(
                        session,
                        self._competition_id,
                        memory_bundle.expected_revision_id,
                    )
                revision = _commit_canonical_bundle_in_session(
                    session,
                    self._competition_id,
                    prepared,
                )
                memory_result = MemoryMutationResult(
                    revision=revision,
                    changes=tuple(
                        proposal.proposed_ref()
                        for proposal in memory_bundle.proposals
                    ),
                )
            elif stored.kind == GenerationKind.BACKTEST.value:
                if memory_bundle.proposals:
                    raise GenerationFinalizationError(
                        "backtest generations cannot commit canonical memory proposals"
                    )
            else:
                raise GenerationFinalizationError(
                    "generation kind does not have a finalization policy"
                )

            completed_at = datetime.now(UTC)
            _finalize_artifact_in_session(
                session,
                self._competition_id,
                FinalizeArtifact(
                    artifact_id=artifact.id,
                    artifact_version_id=version.id,
                ),
                finalized_at=completed_at,
            )
            generation = _succeed_generation_in_session(
                session,
                self._competition_id,
                SucceedGeneration(
                    generation_id=generation_id,
                    submitted_artifact_version_id=version.id,
                ),
                completed_at=completed_at,
            )
        return GenerationFinalizationResult(
            generation=generation,
            memory_result=memory_result,
        )

    def _validate_memory_bundle(
        self,
        stored: StoredGeneration,
        bundle: MemoryMutationBundle,
    ) -> None:
        expected = (
            self._competition_id,
            stored.id,
            stored.input_memory_revision_id,
            stored.competition_season_id,
            stored.week_end,
            stored.knowledge_cutoff_at,
        )
        actual = (
            bundle.competition_id,
            bundle.generation_id,
            bundle.expected_revision_id,
            bundle.competition_season_id,
            bundle.week,
            bundle.knowledge_cutoff_at,
        )
        if actual != expected:
            raise GenerationFinalizationError(
                "completed memory bundle differs from the generation's pinned inputs"
            )


__all__ = [
    "GenerationFinalizationError",
    "GenerationFinalizationResult",
    "GenerationFinalizer",
]
