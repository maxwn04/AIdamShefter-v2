"""Competition-scoped reference validation for complete fact content."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.database.models.memory import EventVersion, MemoryItem, MemoryVersion
from backend.resources.memory.common.errors import (
    CrossCompetitionReferenceError,
    TargetNotFoundError,
    WrongTargetKindError,
)
from backend.resources.memory.common.entity_validation import (
    validate_entity_references,
)
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.common.receipt_validation import (
    validate_api_receipt,
    validate_tool_receipt,
)
from backend.resources.memory.facts.objects import FactContent


@dataclass(frozen=True, slots=True)
class ValidatedFactContent:
    competition_id: UUID
    content: FactContent
    primary_tool_call_generation_id: UUID | None


def validate_fact_content(
    session: Session,
    competition_id: UUID,
    content: FactContent,
) -> ValidatedFactContent:
    """Validate all database-backed fact references in the caller's transaction."""

    validate_entity_references(session, competition_id, content.subjects)
    _validate_originating_events(session, competition_id, content)
    receipt_generation_id = validate_tool_receipt(
        session, competition_id, content.primary_tool_call_id
    )
    validate_api_receipt(session, competition_id, content.primary_api_request_id)
    return ValidatedFactContent(
        competition_id=competition_id,
        content=content,
        primary_tool_call_generation_id=receipt_generation_id,
    )

def _validate_originating_events(
    session: Session,
    competition_id: UUID,
    content: FactContent,
) -> None:
    expected = content.originating_event_version_ids
    if not expected:
        return
    rows = session.execute(
        sa.select(
            MemoryVersion.id,
            MemoryVersion.competition_id,
            MemoryItem.kind,
            EventVersion.version_id.label("typed_event_version_id"),
        )
        .join(MemoryItem, MemoryItem.id == MemoryVersion.item_id)
        .outerjoin(EventVersion, EventVersion.version_id == MemoryVersion.id)
        .where(MemoryVersion.id.in_(set(expected)))
    )
    found = {
        version_id: (scope, kind, typed_event_id)
        for version_id, scope, kind, typed_event_id in rows
    }
    for version_id in expected:
        target = found.get(version_id)
        if target is None:
            raise TargetNotFoundError(version_id, (MemoryKind.EVENT,))
        target_scope, target_kind, typed_event_id = target
        if target_scope != competition_id:
            raise CrossCompetitionReferenceError(
                version_id, competition_id, target_scope
            )
        if target_kind != MemoryKind.EVENT.value:
            raise WrongTargetKindError(
                version_id,
                (MemoryKind.EVENT,),
                MemoryKind(target_kind),
            )
        if typed_event_id is None:
            raise TargetNotFoundError(version_id, (MemoryKind.EVENT,))
