"""Stored-schema codecs for context-note aggregates."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.sql import Select

from backend.database.models.memory import MemoryItem, MemoryVersion
from backend.database.models.memory.context_notes import (
    ContextNote as ContextNoteRow,
)
from backend.database.models.memory.context_notes import (
    ContextNoteVersion,
)
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.context_notes.objects import (
    CompetitionContextNoteIdentity,
    CompetitionSeasonContextNoteIdentity,
    ContextNote,
    ContextNoteContent,
    ContextNoteIdentity,
    FranchiseContextNoteIdentity,
)
from backend.resources.memory.revisions.hashing import StoredSchemaContent


def context_note_rows_statement() -> Select[
    tuple[MemoryItem, MemoryVersion, ContextNoteRow, ContextNoteVersion]
]:
    """Select complete context-note aggregates without exposing storage joins."""

    return (
        sa.select(MemoryItem, MemoryVersion, ContextNoteRow, ContextNoteVersion)
        .join(MemoryVersion, MemoryVersion.item_id == MemoryItem.id)
        .join(ContextNoteRow, ContextNoteRow.item_id == MemoryItem.id)
        .join(ContextNoteVersion, ContextNoteVersion.version_id == MemoryVersion.id)
        .where(MemoryItem.kind == MemoryKind.CONTEXT_NOTE.value)
    )


def decode_context_note(
    item: MemoryItem,
    version: MemoryVersion,
    identity_row: ContextNoteRow,
    stored: ContextNoteVersion,
) -> ContextNote:
    content = _decode_content(version.content_schema_version, stored)
    return ContextNote.model_validate(
        {
            "item": {
                "item_id": item.id,
                "competition_id": item.competition_id,
                "kind": item.kind,
                "agent_key": item.agent_key,
                "created_at": item.created_at,
            },
            "version": {
                "version_id": version.id,
                "revision_number": version.revision_number,
                "content_schema_version": version.content_schema_version,
                "introduced_revision_id": version.introduced_revision_id,
                "retired_revision_id": version.retired_revision_id,
                "competition_season_id": version.competition_season_id,
                "week": version.week,
                "occurred_at": version.occurred_at,
                "creating_generation_id": version.creating_generation_id,
                "creating_tool_call_id": version.creating_tool_call_id,
                "change_reason": version.change_reason,
                "recorded_at": version.recorded_at,
            },
            "note_identity": decode_context_note_identity(identity_row),
            "content": content,
        }
    )


def decode_context_note_identity(row: ContextNoteRow) -> ContextNoteIdentity:
    """Decode the stable scope/key row into its discriminated identity."""

    if row.scope == "competition":
        return CompetitionContextNoteIdentity(note_key=row.note_key)
    if row.scope == "competition_season":
        if row.competition_season_id is None:
            raise ValueError("competition-season note identity is missing its target")
        return CompetitionSeasonContextNoteIdentity(
            competition_season_id=row.competition_season_id,
            note_key=row.note_key,
        )
    if row.scope == "franchise":
        if row.franchise_id is None:
            raise ValueError("franchise note identity is missing its target")
        return FranchiseContextNoteIdentity(
            franchise_id=row.franchise_id,
            note_key=row.note_key,
        )
    raise ValueError(f"unsupported stored context-note scope {row.scope!r}")


def encode_context_note_identity(identity: ContextNoteIdentity) -> dict[str, Any]:
    """Translate one stable typed identity into its storage row fields."""

    competition_season_id = None
    franchise_id = None
    if identity.scope == "competition_season":
        competition_season_id = identity.competition_season_id
    elif identity.scope == "franchise":
        franchise_id = identity.franchise_id
    return {
        "scope": identity.scope,
        "competition_season_id": competition_season_id,
        "franchise_id": franchise_id,
        "note_key": identity.note_key,
    }


def encode_context_note(content: ContextNoteContent) -> dict[str, Any]:
    """Translate complete typed content into the current stored v1 row."""

    return {
        "narrative_text": content.narrative,
        "outlook": content.outlook,
        "status": content.status.value,
        "tags": list(content.tags),
    }


def stored_context_note_content(
    content: ContextNoteContent,
) -> StoredSchemaContent:
    """Encode exact retained v1 logical content for canonical state hashing."""

    if content.schema_version != 1:
        raise ValueError(
            f"unsupported context-note content schema version {content.schema_version}"
        )
    return StoredSchemaContent(
        memory_kind=MemoryKind.CONTEXT_NOTE,
        schema_version=1,
        payload={
            "schema_version": 1,
            "narrative": content.narrative,
            "outlook": content.outlook,
            "status": content.status.value,
            "tags": list(content.tags),
        },
    )


def _decode_content(
    schema_version: int,
    stored: ContextNoteVersion,
) -> ContextNoteContent:
    if schema_version != 1:
        raise ValueError(
            f"unsupported context-note content schema version {schema_version}"
        )
    return ContextNoteContent.model_validate(
        {
            "schema_version": 1,
            "narrative": stored.narrative_text,
            "outlook": stored.outlook,
            "status": stored.status,
            "tags": stored.tags,
        }
    )
