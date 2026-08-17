from __future__ import annotations

from uuid import uuid4

import pytest

from backend.database.models.memory import EventVersion
from backend.resources.memory.common import MemoryKind
from backend.resources.memory.events import EventContent, MatchupEventPayload
from backend.resources.memory.events.codec import (
    _decode_content,
    encode_event,
    stored_event_content,
)


def _matchup() -> EventContent:
    return EventContent.model_validate(
        {
            "event_type": "matchup",
            "headline": "A rivalry result",
            "summary": "The favorite survived a close matchup.",
            "salience": 3,
            "confidence": "inferred",
            "status": "active",
            "details": {
                "kind": "matchup",
                "winner_franchise_id": uuid4(),
                "loser_franchise_id": uuid4(),
                "sleeper_matchup_id": "opaque-matchup-key",
            },
            "source_hints": {"week": 8},
        }
    )


def test_event_v1_codec_round_trips_discriminated_payload() -> None:
    content = _matchup()
    encoded = encode_event(content, receipt_generation_id=None)
    stored = EventVersion(
        version_id=uuid4(),
        competition_id=uuid4(),
        **encoded,
    )

    decoded = _decode_content(1, stored)
    retained = stored_event_content(content)

    assert decoded == content
    assert isinstance(decoded.details, MatchupEventPayload)
    assert retained.memory_kind is MemoryKind.EVENT
    assert retained.schema_version == 1
    assert retained.payload["details"] == content.details.model_dump(mode="python")


def test_event_codec_rejects_unknown_retained_schema_version() -> None:
    content = _matchup()
    stored = EventVersion(
        version_id=uuid4(),
        competition_id=uuid4(),
        **encode_event(content, receipt_generation_id=None),
    )

    with pytest.raises(ValueError, match="unsupported event content schema version 2"):
        _decode_content(2, stored)
