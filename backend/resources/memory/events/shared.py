"""Package-internal event validation and persistence for canonical writes."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from backend.database.models.memory import EventVersion, MemoryItem, MemoryVersion
from backend.resources.memory.common.errors import (
    CrossCompetitionReferenceError,
    StaleItemVersionError,
    TargetNotFoundError,
    WrongTargetKindError,
)
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.events.codec import encode_event
from backend.resources.memory.events.objects import EventContent
from backend.resources.memory.events.validation import (
    ValidatedEventContent,
    validate_event_content,
)
from backend.resources.memory.search_documents.builders.event import (
    build_event_document,
)
from backend.resources.memory.search_documents.shared import insert_search_document


@dataclass(frozen=True, slots=True)
class PreparedEventReplacement:
    validated: ValidatedEventContent
    previous_version: MemoryVersion
    next_revision_number: int


def prepare_event_write(
    session: Session,
    competition_id: UUID,
    content: EventContent,
) -> ValidatedEventContent:
    """Validate a complete create/replacement payload in the active transaction."""

    return validate_event_content(session, competition_id, content)


def prepare_event_replacement(
    session: Session,
    competition_id: UUID,
    item_id: UUID,
    expected_item_revision: int,
    content: EventContent,
) -> PreparedEventReplacement:
    """Validate one complete replacement and resolve its current envelope."""

    item = session.get(MemoryItem, item_id)
    if item is None:
        raise TargetNotFoundError(item_id, (MemoryKind.EVENT,))
    if item.competition_id != competition_id:
        raise CrossCompetitionReferenceError(
            item_id,
            competition_id,
            item.competition_id,
        )
    if item.kind != MemoryKind.EVENT.value:
        raise WrongTargetKindError(
            item_id,
            (MemoryKind.EVENT,),
            MemoryKind(item.kind),
        )
    previous = session.scalar(
        sa.select(MemoryVersion)
        .join(EventVersion, EventVersion.version_id == MemoryVersion.id)
        .where(
            MemoryVersion.item_id == item_id,
            MemoryVersion.competition_id == competition_id,
            MemoryVersion.retired_revision_id.is_(None),
        )
    )
    if previous is None:
        raise TargetNotFoundError(item_id, (MemoryKind.EVENT,))
    if previous.revision_number != expected_item_revision:
        raise StaleItemVersionError(
            item_id,
            expected_item_revision,
            previous.revision_number,
        )
    return PreparedEventReplacement(
        validated=validate_event_content(session, competition_id, content),
        previous_version=previous,
        next_revision_number=previous.revision_number + 1,
    )


def insert_event_version(
    session: Session,
    version: MemoryVersion,
    prepared: ValidatedEventContent,
) -> None:
    """Insert typed content and its derived projection beside a new envelope."""

    content = prepared.content
    if version.competition_id != prepared.competition_id:
        raise CrossCompetitionReferenceError(
            version.id,
            prepared.competition_id,
            version.competition_id,
        )
    if version.content_schema_version != content.schema_version:
        raise ValueError("event schema version does not match version envelope")
    if not inspect(version).persistent:
        raise ValueError("event version envelope must be persisted before content")
    session.add(
        EventVersion(
            version_id=version.id,
            competition_id=version.competition_id,
            **encode_event(
                content,
                prepared.primary_tool_call_generation_id,
            ),
        )
    )
    insert_search_document(session, version, build_event_document(content))
