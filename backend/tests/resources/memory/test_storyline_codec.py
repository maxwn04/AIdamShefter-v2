from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import pytest

from backend.database.models.memory import StorylineVersion
from backend.resources.memory.common import MemoryKind
from backend.resources.memory.storylines import StorylineContent
from backend.resources.memory.storylines.codec import (
    _decode_content,
    encode_storyline,
    stored_storyline_content,
)


FACT_VERSION_ID = UUID("11111111-1111-1111-1111-111111111111")
RELATED_ITEM_ID = UUID("22222222-2222-2222-2222-222222222222")


def _storyline() -> StorylineContent:
    return StorylineContent.model_validate(
        {
            "headline": "A rivalry reaches the playoffs",
            "summary": "The Sharks and Owls meet with a season at stake.",
            "status": "active",
            "arc_type": "rivalry",
            "salience": 5,
            "tags": ["Playoffs", "Rivalry"],
            "subjects": [
                {
                    "kind": "player",
                    "id": "player-7",
                    "role": "counterparty",
                    "display_name": "The Captain",
                },
                {
                    "kind": "franchise",
                    "id": uuid4(),
                    "role": "focus",
                    "display_name": "Sharks",
                },
            ],
            "evidence": [
                {
                    "kind": "fact",
                    "version_id": FACT_VERSION_ID,
                    "role": "support",
                }
            ],
            "related_storylines": [
                {
                    "item_id": RELATED_ITEM_ID,
                    "role": "continuation",
                }
            ],
            "callback_condition": "Revisit after the semifinal.",
            "resolution_summary": None,
        }
    )


def test_storyline_v1_codec_round_trips_complete_content() -> None:
    content = _storyline()
    stored = StorylineVersion(version_id=uuid4(), **encode_storyline(content))

    decoded = _decode_content(1, stored)
    retained = stored_storyline_content(content)

    assert decoded == content
    assert retained.memory_kind is MemoryKind.STORYLINE
    assert retained.schema_version == 1
    evidence = cast(list[dict[str, object]], retained.payload["evidence"])
    assert evidence[0]["version_id"] == FACT_VERSION_ID


def test_storyline_codec_rejects_unknown_retained_schema_version() -> None:
    content = _storyline()
    stored = StorylineVersion(version_id=uuid4(), **encode_storyline(content))

    with pytest.raises(
        ValueError,
        match="unsupported storyline content schema version 2",
    ):
        _decode_content(2, stored)
