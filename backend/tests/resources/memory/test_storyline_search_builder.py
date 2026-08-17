from __future__ import annotations

from uuid import UUID

from backend.resources.memory.common import MemoryKind
from backend.resources.memory.search_documents import (
    STORYLINE_DOCUMENT_BUILDER_VERSION,
    build_storyline_document,
)
from backend.resources.memory.storylines import StorylineContent


FRANCHISE_ID = UUID("11111111-1111-1111-1111-111111111111")
ROSTER_ID = UUID("22222222-2222-2222-2222-222222222222")
FACT_VERSION_ID = UUID("33333333-3333-3333-3333-333333333333")
EVENT_VERSION_ID = UUID("44444444-4444-4444-4444-444444444444")
RELATED_A = UUID("55555555-5555-5555-5555-555555555555")
RELATED_B = UUID("66666666-6666-6666-6666-666666666666")


def _storyline(*, reversed_references: bool = False) -> StorylineContent:
    subjects = [
        {
            "kind": "franchise",
            "id": FRANCHISE_ID,
            "role": "focus",
            "display_name": "Sharks",
        },
        {
            "kind": "season_roster",
            "id": ROSTER_ID,
            "role": "counterparty",
            "display_name": "Owls 2026",
        },
    ]
    evidence = [
        {"kind": "event", "version_id": EVENT_VERSION_ID, "role": "origin"},
        {"kind": "fact", "version_id": FACT_VERSION_ID, "role": "support"},
    ]
    related = [
        {"item_id": RELATED_B, "role": "counterpoint"},
        {"item_id": RELATED_A, "role": "continuation"},
    ]
    tags = ["Rivalry", "Playoffs"]
    if reversed_references:
        subjects.reverse()
        evidence.reverse()
        related.reverse()
        tags.reverse()
    return StorylineContent.model_validate(
        {
            "headline": "The rivalry reaches its reckoning.",
            "summary": "Sharks and Owls meet again in the postseason.",
            "status": "resolved",
            "arc_type": "rivalry",
            "salience": 5,
            "tags": tags,
            "subjects": subjects,
            "evidence": evidence,
            "related_storylines": related,
            "callback_condition": "Return after the semifinal.",
            "resolution_summary": "The Sharks finally won the rematch.",
        }
    )


def test_storyline_projection_normalizes_order_and_flattens_references() -> None:
    projection = build_storyline_document(_storyline())
    reordered = build_storyline_document(_storyline(reversed_references=True))

    assert projection == reordered
    assert projection.kind is MemoryKind.STORYLINE
    assert projection.status == "resolved"
    assert projection.salience == 5
    assert projection.entity_keys == (
        f"franchise:{FRANCHISE_ID}",
        f"roster:{ROSTER_ID}",
    )
    assert projection.evidence_version_ids == (FACT_VERSION_ID, EVENT_VERSION_ID)
    assert projection.related_item_ids == (RELATED_A, RELATED_B)
    assert projection.tags == ("playoffs", "rivalry")
    assert projection.builder_version == STORYLINE_DOCUMENT_BUILDER_VERSION
    assert "focus Sharks" in projection.document_text
    assert f"origin event:{EVENT_VERSION_ID}" in projection.document_text


def test_storyline_projection_hash_covers_complete_content() -> None:
    content = _storyline()
    original = build_storyline_document(content)
    changed_callback = build_storyline_document(
        content.model_copy(update={"callback_condition": "Return after the final."})
    )

    assert original.content_hash != changed_callback.content_hash
    assert original.document_text != changed_callback.document_text
