from __future__ import annotations

from uuid import UUID

from backend.resources.memory.common import MemoryKind
from backend.resources.memory.facts import FactContent
from backend.resources.memory.search_documents import (
    FACT_DOCUMENT_BUILDER_VERSION,
    build_fact_document,
)


FRANCHISE_ID = UUID("11111111-1111-1111-1111-111111111111")
ROSTER_ID = UUID("22222222-2222-2222-2222-222222222222")
EVENT_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
EVENT_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
RECEIPT_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _fact(*, reversed_references: bool = False) -> FactContent:
    subjects = [
        {
            "kind": "franchise",
            "id": FRANCHISE_ID,
            "role": "subject",
            "display_name": "The Sharks",
        },
        {
            "kind": "season_roster",
            "id": ROSTER_ID,
            "role": "subject",
        },
    ]
    events = [EVENT_A, EVENT_B]
    if reversed_references:
        subjects.reverse()
        events.reverse()
    return FactContent.model_validate(
        {
            "claim": "The Sharks won six straight games.",
            "category": "streak",
            "numbers": {"wins": 6, "splits": {"road": 2, "home": 4}},
            "confidence": "source_backed",
            "status": "active",
            "subjects": subjects,
            "originating_event_version_ids": events,
            "primary_api_request_id": RECEIPT_ID,
            "source_hints": {"provider": "Sleeper"},
        }
    )


def test_fact_projection_is_identity_free_and_normalizes_reference_order() -> None:
    projection = build_fact_document(_fact())
    reordered = build_fact_document(_fact(reversed_references=True))

    assert projection == reordered
    assert projection.kind is MemoryKind.FACT
    assert projection.status == "active"
    assert projection.salience is None
    assert projection.entity_keys == (
        f"franchise:{FRANCHISE_ID}",
        f"roster:{ROSTER_ID}",
    )
    assert projection.evidence_version_ids == (EVENT_A, EVENT_B)
    assert projection.related_item_ids == ()
    assert projection.tags == ()
    assert projection.builder_version == FACT_DOCUMENT_BUILDER_VERSION
    assert projection.content_hash == (
        "39871eb6a39a66b3b4d98865a2bbfd42fc0d6b43ef25418f8b226fcee75e37e7"
    )
    assert "The Sharks won six straight games." in projection.document_text
    assert 'numbers:{"splits":{"home":4,"road":2},"wins":6}' in (
        projection.document_text
    )
    assert str(RECEIPT_ID) not in projection.document_text


def test_fact_projection_hash_covers_complete_content_not_persistence_identity(
) -> None:
    content = _fact()
    original = build_fact_document(content)
    changed_receipt = build_fact_document(
        content.model_copy(update={"primary_api_request_id": EVENT_A})
    )

    assert original.document_text == changed_receipt.document_text
    assert original.content_hash != changed_receipt.content_hash
