"""Package-internal trigger validation and persistence for canonical writes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from backend.database.models.memory import MemoryItem, MemoryVersion, TriggerVersion
from backend.resources.memory.common.errors import (
    CrossCompetitionReferenceError,
    StaleItemVersionError,
    TargetNotFoundError,
    WrongTargetKindError,
)
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.search_documents.builders.trigger import (
    build_trigger_document,
)
from backend.resources.memory.search_documents.shared import insert_search_document
from backend.resources.memory.triggers.codec import (
    decode_trigger,
    encode_trigger,
    stored_trigger_content,
    trigger_rows_statement,
)
from backend.resources.memory.triggers.objects import TriggerContent
from backend.resources.memory.triggers.validation import (
    ValidatedTriggerContent,
    validate_trigger_content,
)
from backend.resources.memory.revisions.hashing import StateHashItem, state_hash_item


@dataclass(frozen=True, slots=True)
class PreparedTriggerReplacement:
    validated: ValidatedTriggerContent
    previous_version: MemoryVersion
    next_revision_number: int


def prepare_trigger_write(
    session: Session,
    competition_id: UUID,
    content: TriggerContent,
) -> ValidatedTriggerContent:
    """Validate a complete create/replacement payload in the active transaction."""

    return validate_trigger_content(session, competition_id, content)


def prepare_trigger_replacement(
    session: Session,
    competition_id: UUID,
    item_id: UUID,
    expected_item_revision: int,
    content: TriggerContent,
) -> PreparedTriggerReplacement:
    """Validate one complete replacement and resolve its current envelope."""

    item = session.get(MemoryItem, item_id)
    if item is None:
        raise TargetNotFoundError(item_id, (MemoryKind.TRIGGER,))
    if item.competition_id != competition_id:
        raise CrossCompetitionReferenceError(
            item_id,
            competition_id,
            item.competition_id,
        )
    if item.kind != MemoryKind.TRIGGER.value:
        raise WrongTargetKindError(
            item_id,
            (MemoryKind.TRIGGER,),
            MemoryKind(item.kind),
        )
    previous = session.scalar(
        sa.select(MemoryVersion)
        .join(TriggerVersion, TriggerVersion.version_id == MemoryVersion.id)
        .where(
            MemoryVersion.item_id == item_id,
            MemoryVersion.competition_id == competition_id,
            MemoryVersion.retired_revision_id.is_(None),
        )
    )
    if previous is None:
        raise TargetNotFoundError(item_id, (MemoryKind.TRIGGER,))
    if previous.revision_number != expected_item_revision:
        raise StaleItemVersionError(
            item_id,
            expected_item_revision,
            previous.revision_number,
        )
    return PreparedTriggerReplacement(
        validated=validate_trigger_content(session, competition_id, content),
        previous_version=previous,
        next_revision_number=previous.revision_number + 1,
    )


def insert_trigger_version(
    session: Session,
    version: MemoryVersion,
    prepared: ValidatedTriggerContent,
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
        raise ValueError("trigger schema version does not match version envelope")
    if not inspect(version).persistent:
        raise ValueError("trigger version envelope must be persisted before content")
    session.add(
        TriggerVersion(
            version_id=version.id,
            competition_id=version.competition_id,
            **encode_trigger(content),
        )
    )
    insert_search_document(session, version, build_trigger_document(content))


def trigger_persister(
    content: TriggerContent,
) -> Callable[[Session, MemoryItem, MemoryVersion], None]:
    def persist(session: Session, _item: MemoryItem, version: MemoryVersion) -> None:
        prepared = prepare_trigger_write(session, version.competition_id, content)
        insert_trigger_version(session, version, prepared)

    return persist


def read_trigger_state(
    session: Session,
    competition_id: UUID,
) -> tuple[StateHashItem, ...]:
    rows = session.execute(
        trigger_rows_statement().where(
            MemoryItem.competition_id == competition_id,
            MemoryVersion.retired_revision_id.is_(None),
        )
    ).all()
    return tuple(
        state_hash_item(
            item_id=item.id,
            kind=MemoryKind.TRIGGER,
            agent_key=item.agent_key,
            version_id=version.id,
            revision_number=version.revision_number,
            content_schema_version=version.content_schema_version,
            competition_season_id=version.competition_season_id,
            week=version.week,
            occurred_at=version.occurred_at,
            content=stored_trigger_content(
                decode_trigger(item, version, stored).content
            ),
        )
        for item, version, stored in rows
    )
