"""Package-internal fact validation and persistence for canonical writes."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from backend.database.models.memory import FactVersion, MemoryItem, MemoryVersion
from backend.resources.memory.common.errors import (
    CrossCompetitionReferenceError,
    StaleItemVersionError,
    TargetNotFoundError,
    WrongTargetKindError,
)
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.facts.codec import encode_fact
from backend.resources.memory.facts.objects import FactContent
from backend.resources.memory.facts.validation import (
    ValidatedFactContent,
    validate_fact_content,
)
from backend.resources.memory.search_documents.builders.fact import (
    build_fact_document,
)
from backend.resources.memory.search_documents.shared import insert_search_document


@dataclass(frozen=True, slots=True)
class PreparedFactReplacement:
    validated: ValidatedFactContent
    previous_version: MemoryVersion
    next_revision_number: int


def prepare_fact_write(
    session: Session,
    competition_id: UUID,
    content: FactContent,
) -> ValidatedFactContent:
    """Validate a complete create/replacement payload in the active transaction."""

    return validate_fact_content(session, competition_id, content)


def prepare_fact_replacement(
    session: Session,
    competition_id: UUID,
    item_id: UUID,
    expected_item_revision: int,
    content: FactContent,
) -> PreparedFactReplacement:
    """Validate one complete replacement and resolve its current envelope."""

    item = session.get(MemoryItem, item_id)
    if item is None:
        raise TargetNotFoundError(item_id, (MemoryKind.FACT,))
    if item.competition_id != competition_id:
        raise CrossCompetitionReferenceError(
            item_id,
            competition_id,
            item.competition_id,
        )
    if item.kind != MemoryKind.FACT.value:
        raise WrongTargetKindError(
            item_id,
            (MemoryKind.FACT,),
            MemoryKind(item.kind),
        )
    previous = session.scalar(
        sa.select(MemoryVersion)
        .join(FactVersion, FactVersion.version_id == MemoryVersion.id)
        .where(
            MemoryVersion.item_id == item_id,
            MemoryVersion.competition_id == competition_id,
            MemoryVersion.retired_revision_id.is_(None),
        )
    )
    if previous is None:
        raise TargetNotFoundError(item_id, (MemoryKind.FACT,))
    if previous.revision_number != expected_item_revision:
        raise StaleItemVersionError(
            item_id,
            expected_item_revision,
            previous.revision_number,
        )
    return PreparedFactReplacement(
        validated=validate_fact_content(session, competition_id, content),
        previous_version=previous,
        next_revision_number=previous.revision_number + 1,
    )


def insert_fact_version(
    session: Session,
    version: MemoryVersion,
    prepared: ValidatedFactContent,
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
        raise ValueError("fact schema version does not match version envelope")
    # RevisionManager owns generic envelope ordering. Enforce that boundary
    # here so a future caller gets a local contract failure instead of an
    # opaque foreign-key violation during the transaction's final flush.
    if not inspect(version).persistent:
        raise ValueError("fact version envelope must be persisted before content")
    session.add(
        FactVersion(
            version_id=version.id,
            competition_id=version.competition_id,
            **encode_fact(
                content,
                prepared.primary_tool_call_generation_id,
            ),
        )
    )
    insert_search_document(session, version, build_fact_document(content))
