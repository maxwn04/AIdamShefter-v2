"""Competition-scoped validation for stable context-note identities."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.database.models.core import CompetitionSeason, Franchise
from backend.resources.memory.common.errors import (
    CrossCompetitionEntityReferenceError,
    EntityReferenceNotFoundError,
)
from backend.resources.memory.context_notes.objects import (
    ContextNoteContent,
    ContextNoteIdentity,
)


@dataclass(frozen=True, slots=True)
class ValidatedContextNote:
    competition_id: UUID
    identity: ContextNoteIdentity
    content: ContextNoteContent


def validate_context_note(
    session: Session,
    competition_id: UUID,
    identity: ContextNoteIdentity,
    content: ContextNoteContent,
) -> ValidatedContextNote:
    """Validate one complete context-note aggregate in the transaction."""

    if identity.scope == "competition_season":
        _validate_scope_target(
            session,
            competition_id,
            "season",
            identity.competition_season_id,
        )
    elif identity.scope == "franchise":
        _validate_scope_target(
            session,
            competition_id,
            "franchise",
            identity.franchise_id,
        )
    return ValidatedContextNote(
        competition_id=competition_id,
        identity=identity,
        content=content,
    )


def _validate_scope_target(
    session: Session,
    competition_id: UUID,
    entity_kind: str,
    entity_id: UUID,
) -> None:
    model = CompetitionSeason if entity_kind == "season" else Franchise
    actual_scope = session.scalar(
        sa.select(model.competition_id).where(model.id == entity_id)
    )
    if actual_scope is None:
        raise EntityReferenceNotFoundError(entity_kind, entity_id)
    if actual_scope != competition_id:
        raise CrossCompetitionEntityReferenceError(
            entity_kind,
            entity_id,
            competition_id,
        )
