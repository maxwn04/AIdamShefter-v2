"""Competition-scoped append manager for durable artifact revisions."""

from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database.models.reporting import AICall as StoredAICall
from backend.database.models.reporting import Artifact as StoredArtifact
from backend.database.models.reporting import ArtifactVersion as StoredArtifactVersion
from backend.database.models.reporting import Generation as StoredGeneration
from backend.database.models.reporting import ToolCall as StoredToolCall
from backend.database.sessions import (
    SessionFactory,
    read_only_session,
    transaction_session,
)
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.reporting.artifact_versions.errors import (
    ArtifactVersionConcurrencyConflict,
    ArtifactVersionLifecycleConflict,
    ArtifactVersionProvenanceConflict,
    ArtifactVersionResourceNotFound,
)
from backend.resources.reporting.artifact_versions.objects import (
    AppendArtifactVersion,
    ArtifactVersion,
    ArtifactVersionPage,
    ArtifactVersionQuery,
    ArtifactVersionSummary,
)


class ArtifactVersionManager:
    """Own hash-verified appends, revision allocation, and scoped reads."""

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

    def append_artifact_version(
        self,
        command: AppendArtifactVersion,
    ) -> ArtifactVersion:
        try:
            with transaction_session(self._session_factory) as session:
                artifact, generation = self._load_artifact_with_generation(
                    session, command.artifact_id, lock=True
                )
                if generation.status != "running":
                    raise ArtifactVersionLifecycleConflict(
                        generation.id,
                        "artifact versions can be appended only for a running generation",
                        actual_status=generation.status,
                    )
                if artifact.finalized_version_id is not None:
                    raise ArtifactVersionLifecycleConflict(
                        artifact.id,
                        "finalized artifacts cannot accept new versions",
                        actual_status="finalized",
                    )
                latest = session.scalar(
                    sa.select(StoredArtifactVersion)
                    .where(StoredArtifactVersion.artifact_id == artifact.id)
                    .order_by(StoredArtifactVersion.revision_number.desc())
                    .limit(1)
                )
                self._validate_provenance(session, generation.id, command)
                if (
                    latest is not None
                    and latest.content_hash == command.content_hash
                    and latest.content == command.content
                ):
                    return _decode(latest)
                stored = StoredArtifactVersion(
                    id=uuid4(),
                    artifact_id=artifact.id,
                    generation_id=generation.id,
                    revision_number=(
                        latest.revision_number + 1 if latest is not None else 1
                    ),
                    content=command.content,
                    content_hash=command.content_hash,
                    source_ai_call_id=command.source_ai_call_id,
                    source_tool_call_id=command.source_tool_call_id,
                )
                session.add(stored)
                session.flush()
                return _decode(stored)
        except IntegrityError:
            raise ArtifactVersionConcurrencyConflict(
                "artifact revision identity is already allocated"
            ) from None

    def get(self, artifact_version_id: UUID) -> ArtifactVersion:
        with read_only_session(self._session_factory) as session:
            return _decode(self._load(session, artifact_version_id))

    def list(self, query: ArtifactVersionQuery) -> ArtifactVersionPage:
        with read_only_session(self._session_factory) as session:
            artifact, _ = self._load_artifact_with_generation(
                session, query.artifact_id
            )
            condition = StoredArtifactVersion.artifact_id == artifact.id
            total = cast(
                int,
                session.scalar(
                    sa.select(sa.func.count())
                    .select_from(StoredArtifactVersion)
                    .where(condition)
                ),
            )
            rows = session.scalars(
                sa.select(StoredArtifactVersion)
                .where(condition)
                .order_by(StoredArtifactVersion.revision_number.asc())
                .limit(query.limit)
                .offset(query.offset)
            ).all()
            return ArtifactVersionPage(
                items=tuple(_decode_summary(row) for row in rows),
                total=total,
                limit=query.limit,
                offset=query.offset,
            )

    def _validate_provenance(
        self,
        session: Session,
        generation_id: UUID,
        command: AppendArtifactVersion,
    ) -> None:
        ai_call: StoredAICall | None = None
        if command.source_ai_call_id is not None:
            ai_call = session.scalar(
                sa.select(StoredAICall).where(
                    StoredAICall.id == command.source_ai_call_id,
                    StoredAICall.generation_id == generation_id,
                )
            )
            if ai_call is None:
                raise ArtifactVersionResourceNotFound(
                    "ai_call", command.source_ai_call_id
                )
        if command.source_tool_call_id is None:
            return
        tool_call = session.scalar(
            sa.select(StoredToolCall).where(
                StoredToolCall.id == command.source_tool_call_id,
                StoredToolCall.generation_id == generation_id,
            )
        )
        if tool_call is None:
            raise ArtifactVersionResourceNotFound(
                "tool_call", command.source_tool_call_id
            )
        if ai_call is not None and tool_call.ai_call_id != ai_call.id:
            raise ArtifactVersionProvenanceConflict(
                "source tool call does not belong to the source AI call"
            )

    def _load(
        self,
        session: Session,
        artifact_version_id: UUID,
    ) -> StoredArtifactVersion:
        stored = session.scalar(
            sa.select(StoredArtifactVersion)
            .join(
                StoredGeneration,
                StoredGeneration.id == StoredArtifactVersion.generation_id,
            )
            .where(
                StoredArtifactVersion.id == artifact_version_id,
                StoredGeneration.competition_id == self._competition_id,
            )
        )
        if stored is None:
            raise ArtifactVersionResourceNotFound(
                "artifact_version", artifact_version_id
            )
        return stored

    def _load_artifact_with_generation(
        self,
        session: Session,
        artifact_id: UUID,
        *,
        lock: bool = False,
    ) -> tuple[StoredArtifact, StoredGeneration]:
        statement = (
            sa.select(StoredArtifact, StoredGeneration)
            .join(
                StoredGeneration,
                StoredGeneration.id == StoredArtifact.generation_id,
            )
            .where(
                StoredArtifact.id == artifact_id,
                StoredGeneration.competition_id == self._competition_id,
            )
        )
        if lock:
            statement = statement.with_for_update(
                of=(StoredGeneration, StoredArtifact)
            )
        row = session.execute(statement).one_or_none()
        if row is None:
            raise ArtifactVersionResourceNotFound("artifact", artifact_id)
        return row._tuple()


def _decode(stored: StoredArtifactVersion) -> ArtifactVersion:
    return ArtifactVersion(
        id=stored.id,
        artifact_id=stored.artifact_id,
        generation_id=stored.generation_id,
        revision_number=stored.revision_number,
        content=stored.content,
        content_hash=stored.content_hash,
        source_ai_call_id=stored.source_ai_call_id,
        source_tool_call_id=stored.source_tool_call_id,
        created_at=stored.created_at,
    )


def _decode_summary(stored: StoredArtifactVersion) -> ArtifactVersionSummary:
    return ArtifactVersionSummary(
        id=stored.id,
        artifact_id=stored.artifact_id,
        generation_id=stored.generation_id,
        revision_number=stored.revision_number,
        content_hash=stored.content_hash,
        source_ai_call_id=stored.source_ai_call_id,
        source_tool_call_id=stored.source_tool_call_id,
        created_at=stored.created_at,
    )


__all__ = ["ArtifactVersionManager"]
