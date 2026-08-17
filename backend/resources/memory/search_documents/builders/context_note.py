from __future__ import annotations

import hashlib
import json
from typing import Any, Final, cast

from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.context_notes.objects import (
    ContextNoteContent,
    ContextNoteIdentity,
)
from backend.resources.memory.search_documents.objects import (
    SearchDocumentProjection,
)

CONTEXT_NOTE_DOCUMENT_BUILDER_VERSION: Final = 1


def build_context_note_document(
    identity: ContextNoteIdentity,
    content: ContextNoteContent,
) -> SearchDocumentProjection:
    """Deterministically flatten a complete context-note aggregate."""

    entity_keys = _entity_keys(identity)
    tags = tuple(sorted(set(content.tags)))
    text_parts = [
        content.narrative,
        f"status: {content.status.value}",
        f"scope: {_scope_text(identity)}",
        f"note key: {identity.note_key}",
    ]
    if content.outlook is not None:
        text_parts.append(f"outlook: {content.outlook}")
    if tags:
        text_parts.append(f"tags: {' '.join(tags)}")

    return SearchDocumentProjection(
        kind=MemoryKind.CONTEXT_NOTE,
        status=content.status.value,
        entity_keys=entity_keys,
        tags=tags,
        document_text="\n".join(text_parts),
        builder_version=CONTEXT_NOTE_DOCUMENT_BUILDER_VERSION,
        content_hash=_context_note_content_hash(identity, content),
    )


def _entity_keys(identity: ContextNoteIdentity) -> tuple[str, ...]:
    if identity.scope == "competition_season":
        return (f"season:{identity.competition_season_id}",)
    if identity.scope == "franchise":
        return (f"franchise:{identity.franchise_id}",)
    return ()


def _scope_text(identity: ContextNoteIdentity) -> str:
    if identity.scope == "competition_season":
        return f"competition season {identity.competition_season_id}"
    if identity.scope == "franchise":
        return f"franchise {identity.franchise_id}"
    return "competition"


def _context_note_content_hash(
    identity: ContextNoteIdentity,
    content: ContextNoteContent,
) -> str:
    serialized = _canonical_json(
        _canonical_context_note_aggregate(identity, content)
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _canonical_context_note_aggregate(
    identity: ContextNoteIdentity,
    content: ContextNoteContent,
) -> dict[str, Any]:
    dumped = cast(dict[str, Any], content.model_dump(mode="json"))
    tags = cast(list[str], dumped["tags"])
    dumped["tags"] = sorted(set(tags))
    return {
        "memory_kind": content.memory_kind.value,
        "identity": identity.model_dump(mode="json"),
        "content": dumped,
    }


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
