from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import TypeAdapter

from backend.database.models.memory.context_notes import (
    ContextNote as ContextNoteRow,
)
from backend.database.models.memory.context_notes import (
    ContextNoteVersion,
)
from backend.resources.memory.common import MemoryKind
from backend.resources.memory.context_notes import (
    ContextNoteContent,
    ContextNoteIdentity,
    ContextNoteStatus,
)
from backend.resources.memory.context_notes.codec import (
    _decode_content,
    decode_context_note_identity,
    encode_context_note,
    encode_context_note_identity,
    stored_context_note_content,
)

SEASON_ID = UUID("11111111-1111-1111-1111-111111111111")
FRANCHISE_ID = UUID("22222222-2222-2222-2222-222222222222")


@pytest.mark.parametrize(
    "identity_payload",
    [
        {"scope": "competition", "note_key": "league_voice"},
        {
            "scope": "competition_season",
            "competition_season_id": SEASON_ID,
            "note_key": "playoff_race",
        },
        {
            "scope": "franchise",
            "franchise_id": FRANCHISE_ID,
            "note_key": "outlook",
        },
    ],
)
def test_context_note_v1_codec_round_trips_each_identity_scope(
    identity_payload: dict[str, object],
) -> None:
    identity = TypeAdapter(ContextNoteIdentity).validate_python(identity_payload)
    content = ContextNoteContent(
        narrative="The rebuild is ahead of schedule.",
        outlook="Contend next season.",
        status=ContextNoteStatus.ACTIVE,
        tags=["rebuild", "young-core"],
    )
    identity_row = ContextNoteRow(
        item_id=uuid4(),
        competition_id=uuid4(),
        **encode_context_note_identity(identity),
    )
    version_row = ContextNoteVersion(
        version_id=uuid4(),
        **encode_context_note(content),
    )

    assert decode_context_note_identity(identity_row) == identity
    assert _decode_content(1, version_row) == content
    retained = stored_context_note_content(content)
    assert retained.memory_kind is MemoryKind.CONTEXT_NOTE
    assert retained.schema_version == 1
    assert retained.payload["tags"] == ["rebuild", "young-core"]


def test_context_note_codec_rejects_unknown_retained_schema_version() -> None:
    content = ContextNoteContent(
        narrative="League-wide context.",
        status=ContextNoteStatus.ACTIVE,
        tags=[],
    )
    version_row = ContextNoteVersion(
        version_id=uuid4(),
        **encode_context_note(content),
    )

    with pytest.raises(
        ValueError,
        match="unsupported context-note content schema version 2",
    ):
        _decode_content(2, version_row)
