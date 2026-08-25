"""Competition-scoped manager for durable artifact identities."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database.models.reporting import Artifact as StoredArtifact
from backend.database.models.reporting import ArtifactVersion as StoredArtifactVersion
from backend.database.models.reporting import Generation as StoredGeneration
from backend.database.sessions import (
    SessionFactory,
    read_only_session,
    transaction_session,
)
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.reporting.artifacts.errors import (
    ArtifactConcurrencyConflict,
    ArtifactLifecycleConflict,
    ArtifactMediaTypeConflict,
    ArtifactResourceNotFound,
)
from backend.resources.reporting.artifacts.objects import (
    Artifact,
    ArtifactPage,
    ArtifactQuery,
    ArtifactSummary,
    CreateArtifact,
    FinalizeArtifact,
)


class ArtifactManager:
    """Own stable path identities, final selection, and scoped reads."""

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

    def create_artifact(self, command: CreateArtifact) -> Artifact:
        try:
            with transaction_session(self._session_factory) as session:
                generation = self._load_generation(
                    session, command.generation_id, lock=True
                )
                self._require_running(generation)
                existing = session.scalar(
                    sa.select(StoredArtifact).where(
                        StoredArtifact.generation_id == generation.id,
                        StoredArtifact.path == command.path,
                    )
                )
                if existing is not None:
                    if existing.media_type != command.media_type:
                        raise ArtifactMediaTypeConflict(
                            command.path,
                            requested_media_type=command.media_type,
                            actual_media_type=existing.media_type,
                        )
                    return _decode(existing)
                stored = StoredArtifact(
                    id=uuid4(),
                    generation_id=generation.id,
                    path=command.path,
                    media_type=command.media_type,
                )
                session.add(stored)
                session.flush()
                return _decode(stored)
        except IntegrityError:
            raise ArtifactConcurrencyConflict(
                "artifact path identity is already allocated"
            ) from None

    def finalize_artifact(self, command: FinalizeArtifact) -> Artifact:
        with transaction_session(self._session_factory) as session:
            return _finalize_artifact_in_session(
                session,
                self._competition_id,
                command,
            )

    def get(self, artifact_id: UUID) -> Artifact:
        with read_only_session(self._session_factory) as session:
            stored, _ = self._load_with_generation(session, artifact_id)
            return _decode(stored)

    def list(self, query: ArtifactQuery) -> ArtifactPage:
        with read_only_session(self._session_factory) as session:
            self._load_generation(session, query.generation_id)
            conditions: list[sa.ColumnElement[bool]] = [
                StoredArtifact.generation_id == query.generation_id
            ]
            if query.finalized is True:
                conditions.append(StoredArtifact.finalized_version_id.is_not(None))
            elif query.finalized is False:
                conditions.append(StoredArtifact.finalized_version_id.is_(None))
            total = cast(
                int,
                session.scalar(
                    sa.select(sa.func.count())
                    .select_from(StoredArtifact)
                    .where(*conditions)
                ),
            )
            version_summary = (
                sa.select(
                    StoredArtifactVersion.artifact_id.label("artifact_id"),
                    sa.func.count(StoredArtifactVersion.id).label(
                        "revision_count"
                    ),
                    sa.func.max(StoredArtifactVersion.created_at).label(
                        "latest_version_at"
                    ),
                )
                .where(
                    StoredArtifactVersion.generation_id == query.generation_id
                )
                .group_by(StoredArtifactVersion.artifact_id)
                .subquery()
            )
            rows = session.execute(
                sa.select(
                    StoredArtifact,
                    sa.func.coalesce(version_summary.c.revision_count, 0).label(
                        "revision_count"
                    ),
                    version_summary.c.latest_version_at,
                )
                .outerjoin(
                    version_summary,
                    version_summary.c.artifact_id == StoredArtifact.id,
                )
                .where(*conditions)
                .order_by(StoredArtifact.path.asc(), StoredArtifact.id.asc())
                .limit(query.limit)
                .offset(query.offset)
            ).all()
            return ArtifactPage(
                items=tuple(
                    _decode_summary(
                        row._mapping[StoredArtifact],
                        revision_count=row._mapping["revision_count"],
                        latest_version_at=row._mapping["latest_version_at"],
                    )
                    for row in rows
                ),
                total=total,
                limit=query.limit,
                offset=query.offset,
            )

    def _load_with_generation(
        self,
        session: Session,
        artifact_id: UUID,
        *,
        lock: bool = False,
    ) -> tuple[StoredArtifact, StoredGeneration]:
        return _load_artifact_with_generation_in_session(
            session,
            self._competition_id,
            artifact_id,
            lock=lock,
        )

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
            raise ArtifactResourceNotFound("generation", generation_id)
        return stored

    @staticmethod
    def _require_running(generation: StoredGeneration) -> None:
        if generation.status != "running":
            raise ArtifactLifecycleConflict(
                generation.id,
                "artifacts can change only for a running generation",
                actual_status=generation.status,
            )


def _decode(stored: StoredArtifact) -> Artifact:
    return Artifact(
        id=stored.id,
        generation_id=stored.generation_id,
        path=stored.path,
        media_type=stored.media_type,
        finalized_version_id=stored.finalized_version_id,
        finalized_at=stored.finalized_at,
        created_at=stored.created_at,
    )


def _decode_summary(
    stored: StoredArtifact,
    *,
    revision_count: int,
    latest_version_at: datetime | None,
) -> ArtifactSummary:
    return ArtifactSummary.model_validate(
        {
            **_decode(stored).model_dump(),
            "revision_count": revision_count,
            "latest_version_at": latest_version_at,
        }
    )


def _resolve_exact_artifact_version_in_session(
    session: Session,
    competition_id: UUID,
    *,
    generation_id: UUID,
    path: str,
    media_type: str,
    revision_number: int,
    content: str,
    content_hash: str,
) -> tuple[StoredArtifact, StoredArtifactVersion]:
    """Lock and resolve an exact reporter snapshot without path role inference."""

    row = session.execute(
        sa.select(StoredArtifact, StoredArtifactVersion)
        .join(
            StoredArtifactVersion,
            StoredArtifactVersion.artifact_id == StoredArtifact.id,
        )
        .join(
            StoredGeneration,
            StoredGeneration.id == StoredArtifact.generation_id,
        )
        .where(
            StoredGeneration.id == generation_id,
            StoredGeneration.competition_id == competition_id,
            StoredArtifact.path == path,
            StoredArtifact.media_type == media_type,
            StoredArtifactVersion.generation_id == generation_id,
            StoredArtifactVersion.revision_number == revision_number,
            StoredArtifactVersion.content_hash == content_hash,
            StoredArtifactVersion.content == content,
        )
        .with_for_update(of=(StoredArtifact, StoredArtifactVersion))
    ).one_or_none()
    if row is None:
        raise ArtifactConcurrencyConflict(
            "reporter submission does not match a durable artifact version"
        )
    artifact, version = row._tuple()
    latest_revision = session.scalar(
        sa.select(sa.func.max(StoredArtifactVersion.revision_number)).where(
            StoredArtifactVersion.artifact_id == artifact.id
        )
    )
    if version.revision_number != latest_revision:
        raise ArtifactConcurrencyConflict(
            "reporter submission must select the latest durable artifact version"
        )
    return artifact, version


def _load_artifact_with_generation_in_session(
    session: Session,
    competition_id: UUID,
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
            StoredGeneration.competition_id == competition_id,
        )
    )
    if lock:
        statement = statement.with_for_update(of=(StoredGeneration, StoredArtifact))
    row = session.execute(statement).one_or_none()
    if row is None:
        raise ArtifactResourceNotFound("artifact", artifact_id)
    return row._tuple()


def _finalize_artifact_in_session(
    session: Session,
    competition_id: UUID,
    command: FinalizeArtifact,
    *,
    finalized_at: datetime | None = None,
) -> Artifact:
    """Finalize an artifact inside a caller-owned transaction."""

    stored, generation = _load_artifact_with_generation_in_session(
        session,
        competition_id,
        command.artifact_id,
        lock=True,
    )
    if stored.finalized_version_id is not None:
        if stored.finalized_version_id == command.artifact_version_id:
            return _decode(stored)
        raise ArtifactLifecycleConflict(
            stored.id,
            "artifact finalization is immutable",
            actual_status="finalized",
        )
    ArtifactManager._require_running(generation)
    selected = session.scalar(
        sa.select(StoredArtifactVersion).where(
            StoredArtifactVersion.id == command.artifact_version_id,
            StoredArtifactVersion.artifact_id == stored.id,
            StoredArtifactVersion.generation_id == stored.generation_id,
        )
    )
    if selected is None:
        raise ArtifactResourceNotFound("artifact_version", command.artifact_version_id)
    latest_revision = session.scalar(
        sa.select(sa.func.max(StoredArtifactVersion.revision_number)).where(
            StoredArtifactVersion.artifact_id == stored.id
        )
    )
    if selected.revision_number != latest_revision:
        raise ArtifactConcurrencyConflict(
            "only the latest artifact version can be finalized"
        )
    stored.finalized_version_id = selected.id
    stored.finalized_at = finalized_at or datetime.now(UTC)
    session.flush()
    return _decode(stored)


__all__ = ["ArtifactManager"]
