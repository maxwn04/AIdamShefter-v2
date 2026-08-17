from __future__ import annotations

from uuid import UUID

from pydantic import TypeAdapter

from backend.resources.memory.common import MemoryKind
from backend.resources.memory.context_notes import (
    ContextNoteContent,
    ContextNoteIdentity,
    ContextNoteStatus,
)
from backend.resources.memory.search_documents import (
    CONTEXT_NOTE_DOCUMENT_BUILDER_VERSION,
    build_context_note_document,
)

SEASON_ID = UUID("11111111-1111-1111-1111-111111111111")
FRANCHISE_ID = UUID("22222222-2222-2222-2222-222222222222")


def _identity(payload: dict[str, object]) -> ContextNoteIdentity:
    return TypeAdapter(ContextNoteIdentity).validate_python(payload)


def _content() -> ContextNoteContent:
    return ContextNoteContent(
        narrative="The roster is built around a young core.",
        outlook="One move away from contention.",
        status=ContextNoteStatus.ACTIVE,
        tags=["identity", "contender"],
    )


def test_context_note_projection_flattens_scope_key_and_content() -> None:
    projection = build_context_note_document(
        _identity(
            {
                "scope": "franchise",
                "franchise_id": FRANCHISE_ID,
                "note_key": "team_identity",
            }
        ),
        _content(),
    )

    assert projection.kind is MemoryKind.CONTEXT_NOTE
    assert projection.status == "active"
    assert projection.entity_keys == (f"franchise:{FRANCHISE_ID}",)
    assert projection.tags == ("contender", "identity")
    assert projection.builder_version == CONTEXT_NOTE_DOCUMENT_BUILDER_VERSION
    assert "note key: team_identity" in projection.document_text
    assert "outlook: One move away from contention." in projection.document_text


def test_context_note_projection_hash_covers_identity_and_complete_content() -> None:
    competition = _identity({"scope": "competition", "note_key": "weekly_outlook"})
    season = _identity(
        {
            "scope": "competition_season",
            "competition_season_id": SEASON_ID,
            "note_key": "weekly_outlook",
        }
    )
    content = _content()

    original = build_context_note_document(competition, content)
    new_identity = build_context_note_document(season, content)
    archived = build_context_note_document(
        competition,
        content.model_copy(update={"status": ContextNoteStatus.ARCHIVED}),
    )

    assert original.content_hash != new_identity.content_hash
    assert original.content_hash != archived.content_hash
    assert new_identity.entity_keys == (f"season:{SEASON_ID}",)
