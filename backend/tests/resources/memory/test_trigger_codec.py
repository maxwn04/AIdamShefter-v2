from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from backend.database.models.memory import TriggerVersion
from backend.resources.memory.common import MemoryKind
from backend.resources.memory.triggers import TriggerContent
from backend.resources.memory.triggers.codec import (
    _decode_content,
    encode_trigger,
    stored_trigger_content,
)


SEASON_ID = UUID("11111111-1111-1111-1111-111111111111")
STORYLINE_ID = UUID("22222222-2222-2222-2222-222222222222")
EVENT_ID = UUID("33333333-3333-3333-3333-333333333333")


def _rematch() -> TriggerContent:
    return TriggerContent.model_validate(
        {
            "trigger_type": "rematch",
            "status": "open",
            "fire_policy": "one_shot",
            "target_competition_season_id": SEASON_ID,
            "target_storyline_item_id": STORYLINE_ID,
            "target_week": 8,
            "condition": {
                "kind": "rematch",
                "franchise_ids": [uuid4(), uuid4()],
            },
        }
    )


def _trade_evaluation() -> TriggerContent:
    return TriggerContent.model_validate(
        {
            "trigger_type": "trade_evaluation",
            "status": "satisfied",
            "fire_policy": "until_resolved",
            "target_storyline_item_id": STORYLINE_ID,
            "origin_event_item_id": EVENT_ID,
            "target_at": datetime(2026, 11, 3, 18, 30, tzinfo=UTC),
            "condition": {"kind": "trade_evaluation"},
            "resolution_reason": "The evaluation window closed.",
        }
    )


@pytest.mark.parametrize("content", [_rematch(), _trade_evaluation()])
def test_trigger_v1_codec_round_trips_each_condition(
    content: TriggerContent,
) -> None:
    stored = TriggerVersion(
        version_id=uuid4(),
        competition_id=uuid4(),
        **encode_trigger(content),
    )

    decoded = _decode_content(1, stored)
    retained = stored_trigger_content(content)

    assert decoded == content
    assert retained.memory_kind is MemoryKind.TRIGGER
    assert retained.schema_version == 1
    assert retained.payload["condition"] == content.condition.model_dump(mode="python")


def test_trigger_codec_rejects_unknown_retained_schema_version() -> None:
    content = _rematch()
    stored = TriggerVersion(
        version_id=uuid4(),
        competition_id=uuid4(),
        **encode_trigger(content),
    )

    with pytest.raises(
        ValueError,
        match="unsupported trigger content schema version 2",
    ):
        _decode_content(2, stored)
