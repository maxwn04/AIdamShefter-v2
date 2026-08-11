"""Package-internal concurrency primitives for canonical revision writes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.database.models.memory import CurrentRevision, MemoryRevision
from backend.resources.memory.common.errors import (
    RevisionNotFoundError,
    StaleCanonicalRevisionError,
)


@dataclass(frozen=True, slots=True)
class LockedRevisionParent:
    current_revision_id: UUID
    next_sequence_number: int
    next_lock_version: int


def lock_current_revision(
    session: Session,
    competition_id: UUID,
    expected_revision_id: UUID,
) -> LockedRevisionParent:
    """Lock and validate the parent of a future canonical revision.

    The caller must already own the surrounding transaction. This helper is not
    a public application API; the completed revision manager write operation
    will enclose it with version, projection, and pointer writes atomically.
    """

    statement = (
        sa.select(
            CurrentRevision.current_revision_id,
            CurrentRevision.lock_version,
            MemoryRevision.sequence_number,
        )
        .join(
            MemoryRevision,
            sa.and_(
                MemoryRevision.id == CurrentRevision.current_revision_id,
                MemoryRevision.competition_id == CurrentRevision.competition_id,
            ),
        )
        .where(CurrentRevision.competition_id == competition_id)
        .with_for_update(of=CurrentRevision)
    )
    row = session.execute(statement).one_or_none()
    if row is None:
        raise RevisionNotFoundError(competition_id)
    current_revision_id = cast(UUID, row.current_revision_id)
    lock_version = cast(int, row.lock_version)
    sequence_number = cast(int, row.sequence_number)
    if current_revision_id != expected_revision_id:
        raise StaleCanonicalRevisionError(
            competition_id,
            expected_revision_id,
            current_revision_id,
        )
    return LockedRevisionParent(
        current_revision_id=current_revision_id,
        next_sequence_number=sequence_number + 1,
        next_lock_version=lock_version + 1,
    )
