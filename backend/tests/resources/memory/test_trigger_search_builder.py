from __future__ import annotations

from uuid import UUID

from backend.resources.memory.common import MemoryKind
from backend.resources.memory.search_documents import (
    TRIGGER_DOCUMENT_BUILDER_VERSION,
    build_trigger_document,
)
from backend.resources.memory.triggers import TriggerContent, TriggerStatus


SEASON_ID = UUID("11111111-1111-1111-1111-111111111111")
STORYLINE_ID = UUID("22222222-2222-2222-2222-222222222222")
FRANCHISE_A = UUID("33333333-3333-3333-3333-333333333333")
FRANCHISE_B = UUID("44444444-4444-4444-4444-444444444444")


def _rematch(*, reversed_franchises: bool = False) -> TriggerContent:
    franchises = [FRANCHISE_A, FRANCHISE_B]
    if reversed_franchises:
        franchises.reverse()
    return TriggerContent.model_validate(
        {
            "trigger_type": "rematch",
            "status": "open",
            "fire_policy": "recurring",
            "target_competition_season_id": SEASON_ID,
            "target_storyline_item_id": STORYLINE_ID,
            "target_week": 9,
            "condition": {
                "kind": "rematch",
                "franchise_ids": franchises,
            },
        }
    )


def test_trigger_projection_normalizes_rematch_participants() -> None:
    projection = build_trigger_document(_rematch())
    reordered = build_trigger_document(_rematch(reversed_franchises=True))

    assert projection == reordered
    assert projection.kind is MemoryKind.TRIGGER
    assert projection.status == "open"
    assert projection.entity_keys == (
        f"franchise:{FRANCHISE_A}",
        f"franchise:{FRANCHISE_B}",
        f"season:{SEASON_ID}",
    )
    assert projection.related_item_ids == (STORYLINE_ID,)
    assert projection.builder_version == TRIGGER_DOCUMENT_BUILDER_VERSION
    assert "target week: 9" in projection.document_text


def test_trigger_projection_hash_covers_complete_content() -> None:
    content = _rematch()
    original = build_trigger_document(content)
    resolved = build_trigger_document(
        content.model_copy(
            update={
                "status": TriggerStatus.SATISFIED,
                "resolution_reason": "The rematch was played.",
            }
        )
    )

    assert original.content_hash != resolved.content_hash


def test_scheduled_review_projection_indexes_question_and_storyline() -> None:
    from uuid import uuid4
    from backend.resources.memory.triggers import TriggerContent
    from backend.resources.memory.search_documents import build_trigger_document
    storyline_id = uuid4()
    content = TriggerContent.model_validate({
        "trigger_type": "scheduled_review", "status": "open", "fire_policy": "one_shot",
        "target_competition_season_id": uuid4(), "target_storyline_item_id": storyline_id,
        "target_week": 2, "condition": {"kind": "scheduled_review", "review_question": "Does lineup timing still matter?"},
    })
    projection = build_trigger_document(content)
    assert projection.related_item_ids == (storyline_id,)
    assert "Does lineup timing still matter?" in projection.document_text
    assert "trade evaluation" not in projection.document_text
