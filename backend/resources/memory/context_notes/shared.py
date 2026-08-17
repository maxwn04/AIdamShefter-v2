"""Package-internal context-note validation and canonical persistence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from backend.database.models.memory import MemoryItem, MemoryVersion
from backend.database.models.memory.context_notes import (
    ContextNote as ContextNoteRow,
)
from backend.database.models.memory.context_notes import (
    ContextNoteVersion,
)
from backend.resources.memory.common.errors import (
    CrossCompetitionReferenceError,
    DuplicateContextNoteError,
    StaleItemVersionError,
    TargetNotFoundError,
    WrongTargetKindError,
)
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.context_notes.codec import (
    context_note_rows_statement,
    decode_context_note,
    decode_context_note_identity,
    encode_context_note,
    encode_context_note_identity,
    stored_context_note_content,
)
from backend.resources.memory.context_notes.objects import (
    ContextNoteContent,
    ContextNoteIdentity,
)
from backend.resources.memory.context_notes.validation import (
    ValidatedContextNote,
    validate_context_note,
)
from backend.resources.memory.revisions.hashing import StateHashItem, state_hash_item
from backend.resources.memory.search_documents.builders.context_note import (
    build_context_note_document,
)
from backend.resources.memory.search_documents.shared import insert_search_document


@dataclass(frozen=True, slots=True)
class PreparedContextNoteReplacement:
    validated: ValidatedContextNote
    previous_version: MemoryVersion
    next_revision_number: int


def prepare_context_note_write(
    session: Session,
    competition_id: UUID,
    identity: ContextNoteIdentity,
    content: ContextNoteContent,
) -> ValidatedContextNote:
    """Validate one complete create payload in the active transaction."""

    return validate_context_note(session, competition_id, identity, content)


def prepare_context_note_replacement(
    session: Session,
    competition_id: UUID,
    item_id: UUID,
    expected_item_revision: int,
    content: ContextNoteContent,
) -> PreparedContextNoteReplacement:
    """Resolve a stable note identity and validate a complete replacement."""

    item = session.get(MemoryItem, item_id)
    if item is None:
        raise TargetNotFoundError(item_id, (MemoryKind.CONTEXT_NOTE,))
    if item.competition_id != competition_id:
        raise CrossCompetitionReferenceError(
            item_id,
            competition_id,
            item.competition_id,
        )
    if item.kind != MemoryKind.CONTEXT_NOTE.value:
        raise WrongTargetKindError(
            item_id,
            (MemoryKind.CONTEXT_NOTE,),
            MemoryKind(item.kind),
        )
    identity_row = session.get(ContextNoteRow, item_id)
    if identity_row is None:
        raise TargetNotFoundError(item_id, (MemoryKind.CONTEXT_NOTE,))
    previous = session.scalar(
        sa.select(MemoryVersion)
        .join(ContextNoteVersion, ContextNoteVersion.version_id == MemoryVersion.id)
        .where(
            MemoryVersion.item_id == item_id,
            MemoryVersion.competition_id == competition_id,
            MemoryVersion.retired_revision_id.is_(None),
        )
    )
    if previous is None:
        raise TargetNotFoundError(item_id, (MemoryKind.CONTEXT_NOTE,))
    if previous.revision_number != expected_item_revision:
        raise StaleItemVersionError(
            item_id,
            expected_item_revision,
            previous.revision_number,
        )
    return PreparedContextNoteReplacement(
        validated=validate_context_note(
            session,
            competition_id,
            decode_context_note_identity(identity_row),
            content,
        ),
        previous_version=previous,
        next_revision_number=previous.revision_number + 1,
    )


def insert_context_note_identity(
    session: Session,
    item: MemoryItem,
    prepared: ValidatedContextNote,
) -> None:
    """Insert the stable scope/key identity beside a new item envelope."""

    if item.competition_id != prepared.competition_id:
        raise CrossCompetitionReferenceError(
            item.id,
            prepared.competition_id,
            item.competition_id,
        )
    if item.kind != MemoryKind.CONTEXT_NOTE.value:
        raise WrongTargetKindError(
            item.id,
            (MemoryKind.CONTEXT_NOTE,),
            MemoryKind(item.kind),
        )
    if not inspect(item).persistent:
        raise ValueError("context-note item envelope must be persisted before identity")
    duplicate = session.scalar(
        sa.select(ContextNoteRow.item_id).where(
            ContextNoteRow.scope == prepared.identity.scope,
            ContextNoteRow.note_key == prepared.identity.note_key,
            ContextNoteRow.competition_id == prepared.competition_id,
            ContextNoteRow.competition_season_id
            == getattr(prepared.identity, "competition_season_id", None),
            ContextNoteRow.franchise_id
            == getattr(prepared.identity, "franchise_id", None),
        )
    )
    if duplicate is not None:
        raise DuplicateContextNoteError(
            prepared.identity.scope,
            prepared.identity.note_key,
        )
    identity_row = ContextNoteRow(
        item_id=item.id,
        competition_id=item.competition_id,
        **encode_context_note_identity(prepared.identity),
    )
    session.add(identity_row)
    session.flush((identity_row,))


def insert_context_note_version(
    session: Session,
    version: MemoryVersion,
    prepared: ValidatedContextNote,
) -> None:
    """Insert versioned content and its projection beside a new envelope."""

    content = prepared.content
    if version.competition_id != prepared.competition_id:
        raise CrossCompetitionReferenceError(
            version.id,
            prepared.competition_id,
            version.competition_id,
        )
    if version.content_schema_version != content.schema_version:
        raise ValueError("context-note schema version does not match version envelope")
    if not inspect(version).persistent:
        raise ValueError(
            "context-note version envelope must be persisted before content"
        )
    identity_row = session.get(ContextNoteRow, version.item_id)
    if identity_row is None:
        raise TargetNotFoundError(version.item_id, (MemoryKind.CONTEXT_NOTE,))
    if decode_context_note_identity(identity_row) != prepared.identity:
        raise ValueError("context-note prepared identity does not match its item")
    session.add(
        ContextNoteVersion(
            version_id=version.id,
            **encode_context_note(content),
        )
    )
    insert_search_document(
        session,
        version,
        build_context_note_document(prepared.identity, content),
    )


def context_note_persister(
    operation: str,
    identity: ContextNoteIdentity | None,
    content: ContextNoteContent,
) -> Callable[[Session, MemoryItem, MemoryVersion], None]:
    def persist(session: Session, item: MemoryItem, version: MemoryVersion) -> None:
        resolved_identity = identity
        if operation == "replace":
            identity_row = session.get(ContextNoteRow, item.id)
            if identity_row is None:
                raise TargetNotFoundError(item.id, (MemoryKind.CONTEXT_NOTE,))
            resolved_identity = decode_context_note_identity(identity_row)
        if resolved_identity is None:
            raise ValueError("context-note create is missing its stable identity")
        prepared = prepare_context_note_write(
            session,
            version.competition_id,
            resolved_identity,
            content,
        )
        if operation == "create":
            insert_context_note_identity(session, item, prepared)
        insert_context_note_version(session, version, prepared)

    return persist


def read_context_note_state(
    session: Session,
    competition_id: UUID,
) -> tuple[StateHashItem, ...]:
    rows = session.execute(
        context_note_rows_statement().where(
            MemoryItem.competition_id == competition_id,
            MemoryVersion.retired_revision_id.is_(None),
        )
    ).all()
    result: list[StateHashItem] = []
    for item, version, identity_row, stored in rows:
        note = decode_context_note(item, version, identity_row, stored)
        result.append(
            state_hash_item(
                item_id=item.id,
                kind=MemoryKind.CONTEXT_NOTE,
                agent_key=item.agent_key,
                version_id=version.id,
                revision_number=version.revision_number,
                content_schema_version=version.content_schema_version,
                competition_season_id=version.competition_season_id,
                week=version.week,
                occurred_at=version.occurred_at,
                content=stored_context_note_content(note.content),
                context_note_identity=note.note_identity,
            )
        )
    return tuple(result)
