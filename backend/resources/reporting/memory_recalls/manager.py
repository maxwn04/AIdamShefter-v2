"""Competition-scoped immutable generation memory-recall persistence."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database.models.reporting import Generation as StoredGeneration
from backend.database.models.reporting import (
    GenerationMemoryRecall as StoredGenerationMemoryRecall,
)
from backend.database.sessions import (
    SessionFactory,
    read_only_session,
    transaction_session,
)
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.reporting.generations import (
    GenerationConcurrencyConflict,
    GenerationLifecycleConflict,
    GenerationResourceNotFound,
)
from backend.resources.reporting.memory_recalls.objects import (
    GenerationMemoryRecall,
    RecordGenerationMemoryRecall,
)


class GenerationMemoryRecallManager:
    """Create and read the one recall record owned by a generation."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id

    def record(
        self,
        command: RecordGenerationMemoryRecall,
    ) -> GenerationMemoryRecall:
        try:
            with transaction_session(self._session_factory) as session:
                generation = self._load_generation(
                    session,
                    command.generation_id,
                    lock=True,
                )
                if generation.status != "running":
                    raise GenerationLifecycleConflict(
                        generation.id,
                        "memory recall can be recorded only for a running generation",
                        expected_statuses=("running",),
                        actual_status=generation.status,
                    )
                stored = StoredGenerationMemoryRecall(
                    generation_id=generation.id,
                    status=command.status.value,
                    result_jsonb=command.result,
                    result_text=command.result_text,
                    metadata_jsonb=command.metadata,
                )
                session.add(stored)
                session.flush()
                return _decode(stored)
        except IntegrityError:
            raise GenerationConcurrencyConflict(
                "memory recall is already recorded for this generation"
            ) from None

    def get(self, generation_id: UUID) -> GenerationMemoryRecall | None:
        with read_only_session(self._session_factory) as session:
            self._load_generation(session, generation_id)
            stored = session.get(StoredGenerationMemoryRecall, generation_id)
            return _decode(stored) if stored is not None else None

    def _load_generation(
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


def _decode(stored: StoredGenerationMemoryRecall) -> GenerationMemoryRecall:
    return GenerationMemoryRecall(
        generation_id=stored.generation_id,
        status=stored.status,
        result=stored.result_jsonb,
        result_text=stored.result_text,
        metadata=stored.metadata_jsonb,
        created_at=cast(datetime, stored.created_at),
    )


__all__ = ["GenerationMemoryRecallManager"]
