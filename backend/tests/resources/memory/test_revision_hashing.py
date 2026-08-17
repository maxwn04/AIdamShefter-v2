from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from backend.resources.memory.common import MemoryKind
from backend.resources.memory.facts import FactContent
from backend.resources.memory.facts.codec import stored_fact_content
from backend.resources.memory.revisions.hashing import (
    StateHashItem,
    compute_state_content_hash,
)


COMPETITION_ID = UUID("00000000-0000-0000-0000-000000000001")
ITEM_ID = UUID("11111111-1111-1111-1111-111111111111")
VERSION_ID = UUID("22222222-2222-2222-2222-222222222222")
SEASON_ID = UUID("33333333-3333-3333-3333-333333333333")
EVENT_ID = UUID("44444444-4444-4444-4444-444444444444")


def _content(*, reverse_number_keys: bool = False) -> FactContent:
    nested = {"second": 2, "first": 1}
    numbers = {"z": 3, "a": nested}
    if reverse_number_keys:
        nested = {"first": 1, "second": 2}
        numbers = {"a": nested, "z": 3}
    return FactContent.model_validate(
        {
            "claim": "Comets won 3 straight.",
            "category": "record",
            "numbers": numbers,
            "confidence": "unverified",
            "status": "active",
            "subjects": [
                {
                    "kind": "player",
                    "id": "player-7",
                    "role": "subject",
                    "display_name": "Eclair",
                }
            ],
            "originating_event_version_ids": [EVENT_ID],
        }
    )


def _item(
    *,
    item_id: UUID = ITEM_ID,
    version_id: UUID = VERSION_ID,
    content: FactContent | None = None,
    occurred_at: datetime | None = None,
) -> StateHashItem:
    return StateHashItem(
        item_id=item_id,
        kind=MemoryKind.FACT,
        agent_key="fact:key",
        context_note_identity=None,
        version_id=version_id,
        revision_number=1,
        content_schema_version=1,
        competition_season_id=SEASON_ID,
        week=7,
        occurred_at=occurred_at
        or datetime(2026, 8, 11, 10, 34, 56, 123456, tzinfo=UTC),
        content=stored_fact_content(content or _content()),
    )


def test_sha256_cbor_v1_empty_state_golden_vector() -> None:
    assert compute_state_content_hash(COMPETITION_ID, ()) == (
        "sha256-cbor-v1:69135ef49dcad2242954c6d79dea97ffa1e28151a07a260cd"
        "81bc1dc5d6118b0"
    )


def test_sha256_cbor_v1_fact_golden_vector_and_normalization() -> None:
    expected = (
        "sha256-cbor-v1:49f7fd5b075a98e773cf6119115ddd4d8568fd747d204f34"
        "403ab6f63230ba32"
    )
    assert compute_state_content_hash(COMPETITION_ID, (_item(),)) == expected

    equivalent = _item(
        content=_content(reverse_number_keys=True),
        occurred_at=datetime(
            2026,
            8,
            11,
            12,
            34,
            56,
            123456,
            tzinfo=timezone(timedelta(hours=2)),
        ),
    )
    assert compute_state_content_hash(COMPETITION_ID, (equivalent,)) == expected


def test_state_hash_sorts_items_and_rejects_duplicate_visible_identity() -> None:
    second = _item(
        item_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        version_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
    )
    assert compute_state_content_hash(COMPETITION_ID, (_item(), second)) == (
        compute_state_content_hash(COMPETITION_ID, (second, _item()))
    )

    with pytest.raises(ValueError, match="repeats memory item"):
        compute_state_content_hash(
            COMPETITION_ID,
            (
                _item(),
                _item(version_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")),
            ),
        )

    with pytest.raises(ValueError, match="schema version does not match"):
        compute_state_content_hash(
            COMPETITION_ID,
            (replace(_item(), content_schema_version=2),),
        )
