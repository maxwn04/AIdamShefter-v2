"""Competition-scoped reference validation for complete storyline content."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.database.models.memory import (
    EventVersion,
    FactVersion,
    MemoryItem,
    MemoryVersion,
)
from backend.resources.memory.common.entity_validation import (
    validate_entity_references,
)
from backend.resources.memory.common.errors import (
    CrossCompetitionReferenceError,
    TargetNotFoundError,
    WrongTargetKindError,
)
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.storylines.objects import StorylineContent


@dataclass(frozen=True, slots=True)
class ValidatedStorylineContent:
    competition_id: UUID
    content: StorylineContent


def validate_storyline_content(
    session: Session,
    competition_id: UUID,
    content: StorylineContent,
) -> ValidatedStorylineContent:
    """Validate all database-backed storyline references in the transaction."""

    validate_entity_references(session, competition_id, content.subjects)
    _validate_evidence(session, competition_id, content)
    _validate_related_storylines(session, competition_id, content)
    return ValidatedStorylineContent(
        competition_id=competition_id,
        content=content,
    )


def _validate_evidence(
    session: Session,
    competition_id: UUID,
    content: StorylineContent,
) -> None:
    if not content.evidence:
        return
    expected_ids = {reference.version_id for reference in content.evidence}
    rows = session.execute(
        sa.select(
            MemoryVersion.id,
            MemoryVersion.competition_id,
            MemoryItem.kind,
            FactVersion.version_id.label("typed_fact_version_id"),
            EventVersion.version_id.label("typed_event_version_id"),
        )
        .join(MemoryItem, MemoryItem.id == MemoryVersion.item_id)
        .outerjoin(FactVersion, FactVersion.version_id == MemoryVersion.id)
        .outerjoin(EventVersion, EventVersion.version_id == MemoryVersion.id)
        .where(MemoryVersion.id.in_(expected_ids))
    )
    found = {
        version_id: (scope, kind, typed_fact_id, typed_event_id)
        for version_id, scope, kind, typed_fact_id, typed_event_id in rows
    }
    for reference in content.evidence:
        expected_kind = MemoryKind(reference.kind)
        target = found.get(reference.version_id)
        if target is None:
            raise TargetNotFoundError(reference.version_id, (expected_kind,))
        target_scope, target_kind, typed_fact_id, typed_event_id = target
        if target_scope != competition_id:
            raise CrossCompetitionReferenceError(
                reference.version_id,
                competition_id,
                target_scope,
            )
        if target_kind != expected_kind.value:
            raise WrongTargetKindError(
                reference.version_id,
                (expected_kind,),
                MemoryKind(target_kind),
            )
        typed_id = typed_fact_id if expected_kind is MemoryKind.FACT else typed_event_id
        if typed_id is None:
            raise TargetNotFoundError(reference.version_id, (expected_kind,))


def _validate_related_storylines(
    session: Session,
    competition_id: UUID,
    content: StorylineContent,
) -> None:
    if not content.related_storylines:
        return
    expected_ids = {reference.item_id for reference in content.related_storylines}
    rows = session.execute(
        sa.select(MemoryItem.id, MemoryItem.competition_id, MemoryItem.kind).where(
            MemoryItem.id.in_(expected_ids)
        )
    )
    found = {
        item_id: (scope, kind)
        for item_id, scope, kind in rows
    }
    for reference in content.related_storylines:
        target = found.get(reference.item_id)
        if target is None:
            raise TargetNotFoundError(reference.item_id, (MemoryKind.STORYLINE,))
        target_scope, target_kind = target
        if target_scope != competition_id:
            raise CrossCompetitionReferenceError(
                reference.item_id,
                competition_id,
                target_scope,
            )
        if target_kind != MemoryKind.STORYLINE.value:
            raise WrongTargetKindError(
                reference.item_id,
                (MemoryKind.STORYLINE,),
                MemoryKind(target_kind),
            )
