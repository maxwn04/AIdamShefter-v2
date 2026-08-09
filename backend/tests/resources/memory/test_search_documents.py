from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from backend.resources.memory.objects import (
    ContextNoteContent,
    ContextNoteIdentity,
    DraftPickTradeAsset,
    EventContent,
    EvidenceRef,
    FactContent,
    FranchiseRef,
    MemoryContent,
    MemoryKind,
    PlayerTradeAsset,
    RelatedStorylineRef,
    StorylineContent,
    TradeEventPayload,
    TriggerContent,
    TypedMemoryVersion,
    WeekTriggerCondition,
)
from backend.resources.memory.search_documents import (
    SEARCH_DOCUMENT_BUILDER_VERSION,
    build_search_document,
)


COMPETITION_ID = UUID("00000000-0000-0000-0000-000000000001")
SEASON_ID = UUID("00000000-0000-0000-0000-000000000002")
OTHER_SEASON_ID = UUID("00000000-0000-0000-0000-000000000008")
ITEM_ID = UUID("00000000-0000-0000-0000-000000000003")
VERSION_ID = UUID("00000000-0000-0000-0000-000000000004")
FRANCHISE_ID = UUID("00000000-0000-0000-0000-000000000005")
EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000006")
RELATED_ID = UUID("00000000-0000-0000-0000-000000000007")
ROSTER_ID = UUID("00000000-0000-0000-0000-000000000009")


def _version(
    content: MemoryContent,
    *,
    identity: ContextNoteIdentity | None = None,
    competition_season_id: UUID | None = SEASON_ID,
    week: int | None = 8,
) -> TypedMemoryVersion:
    return TypedMemoryVersion(
        version_id=VERSION_ID,
        item_id=ITEM_ID,
        competition_id=COMPETITION_ID,
        kind=MemoryKind(content.kind),
        content=content,
        content_schema_version=content.schema_version,
        revision_number=1,
        introduced_revision_id=RELATED_ID,
        competition_season_id=competition_season_id,
        week=week,
        creating_generation_id=EVIDENCE_ID,
        recorded_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
        context_note_identity=identity,
    )


STORYLINE_VERSION = _version(
    StorylineContent(
        headline="The Long Collapse",
        summary="The Sharks lost again.",
        status="active",
        arc_type="collapse",
        salience=4,
        tags=("playoffs", "collapse"),
        subjects=(
            FranchiseRef(
                id=FRANCHISE_ID,
                role="focus",
                display_name="Old Sharks",
            ),
        ),
        evidence=(
            EvidenceRef(kind="fact", version_id=EVIDENCE_ID, role="support"),
        ),
        related_storylines=(
            RelatedStorylineRef(item_id=RELATED_ID, role="counterpoint"),
        ),
        callback_condition="If the slide continues",
    )
)

FACT_VERSION = _version(
    FactContent(
        claim="The Sharks have lost three straight.",
        category="streak",
        numbers={"losses": 3},
        confidence="source_backed",
        status="active",
        subjects=(FranchiseRef(id=FRANCHISE_ID, role="subject"),),
        originating_event_version_ids=(EVIDENCE_ID,),
    )
)

TRADE_VERSION = _version(
    EventContent(
        event_type="trade",
        headline="A blockbuster trade",
        summary="The Sharks acquired a quarterback and a first-round pick.",
        salience=5,
        confidence="source_backed",
        status="active",
        details=TradeEventPayload(
            sender_franchise_id=FRANCHISE_ID,
            receiver_franchise_id=RELATED_ID,
            assets=(
                PlayerTradeAsset(player_id="player-1", display_name="QB One"),
                DraftPickTradeAsset(
                    season=2027,
                    round=1,
                    original_season_roster_id=ROSTER_ID,
                ),
            ),
            sleeper_transaction_id="txn-42",
        ),
    )
)

TRIGGER_VERSION = _version(
    TriggerContent(
        trigger_type="week",
        status="open",
        fire_policy="one_shot",
        target_competition_season_id=SEASON_ID,
        target_storyline_item_id=RELATED_ID,
        origin_event_item_id=ITEM_ID,
        target_week=9,
        condition=WeekTriggerCondition(week=9),
    )
)

CONTEXT_VERSION = _version(
    ContextNoteContent(
        narrative="The league rewards patient roster building.",
        outlook="Expect contenders to hoard picks.",
        status="active",
        tags=("dynasty", "strategy"),
    ),
    identity=ContextNoteIdentity(
        scope="franchise",
        note_key="identity",
        franchise_id=FRANCHISE_ID,
    ),
)


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        (
            STORYLINE_VERSION,
            {
                "status": "active",
                "salience": 4,
                "entity_keys": (f"franchise:{FRANCHISE_ID}",),
                "evidence_version_ids": (EVIDENCE_ID,),
                "related_item_ids": (RELATED_ID,),
                "tags": ("collapse", "playoffs"),
                "document_text": "\n".join(
                    (
                        "The Long Collapse",
                        "The Sharks lost again.",
                        "collapse",
                        "active",
                        "collapse",
                        "playoffs",
                        "Old Sharks",
                        "If the slide continues",
                    )
                ),
            },
        ),
        (
            FACT_VERSION,
            {
                "status": "active",
                "salience": None,
                "entity_keys": (f"franchise:{FRANCHISE_ID}",),
                "evidence_version_ids": (EVIDENCE_ID,),
                "related_item_ids": (),
                "tags": (),
                "document_text": "\n".join(
                    (
                        "The Sharks have lost three straight.",
                        "streak",
                        "source_backed",
                        "active",
                        '{"losses":3}',
                        f"franchise:{FRANCHISE_ID}",
                    )
                ),
            },
        ),
        (
            TRADE_VERSION,
            {
                "status": "active",
                "salience": 5,
                "entity_keys": (
                    f"franchise:{FRANCHISE_ID}",
                    f"franchise:{RELATED_ID}",
                    "player:player-1",
                    f"roster:{ROSTER_ID}",
                ),
                "evidence_version_ids": (),
                "related_item_ids": (),
                "tags": (),
                "document_text": "\n".join(
                    (
                        "A blockbuster trade",
                        "The Sharks acquired a quarterback and a first-round pick.",
                        "trade",
                        "source_backed",
                        "active",
                        (
                            '{"assets":[{"display_name":"QB One","kind":"player",'
                            '"player_id":"player-1"},{"kind":"draft_pick",'
                            f'"original_season_roster_id":"{ROSTER_ID}",'
                            '"round":1,"season":2027}],"kind":"trade",'
                            f'"receiver_franchise_id":"{RELATED_ID}",'
                            f'"sender_franchise_id":"{FRANCHISE_ID}",'
                            '"sleeper_transaction_id":"txn-42"}'
                        ),
                        f"franchise:{FRANCHISE_ID}",
                        f"franchise:{RELATED_ID}",
                        "player:player-1",
                        f"roster:{ROSTER_ID}",
                    )
                ),
            },
        ),
        (
            TRIGGER_VERSION,
            {
                "status": "open",
                "salience": None,
                "entity_keys": (f"season:{SEASON_ID}",),
                "evidence_version_ids": (),
                "related_item_ids": tuple(sorted((ITEM_ID, RELATED_ID), key=str)),
                "tags": (),
                "document_text": "\n".join(
                    (
                        "week",
                        "open",
                        "one_shot",
                        "9",
                        '{"kind":"week","week":9}',
                    )
                ),
            },
        ),
        (
            CONTEXT_VERSION,
            {
                "status": "active",
                "salience": None,
                "entity_keys": (f"franchise:{FRANCHISE_ID}",),
                "evidence_version_ids": (),
                "related_item_ids": (),
                "tags": ("dynasty", "strategy"),
                "document_text": "\n".join(
                    (
                        "The league rewards patient roster building.",
                        "Expect contenders to hoard picks.",
                        "active",
                        "franchise",
                        "identity",
                        f"franchise:{FRANCHISE_ID}",
                        "dynasty",
                        "strategy",
                    )
                ),
            },
        ),
    ],
)
def test_build_search_document_has_golden_output(
    version: TypedMemoryVersion,
    expected: dict[str, object],
) -> None:
    document = build_search_document(version)

    for field, value in expected.items():
        assert getattr(document, field) == value
    assert document.version_id == VERSION_ID
    assert document.item_id == ITEM_ID
    assert document.competition_id == COMPETITION_ID
    assert document.builder_version == SEARCH_DOCUMENT_BUILDER_VERSION
    assert len(document.content_hash) == 64
    assert document == build_search_document(version)


def test_typed_trade_flattens_tuple_assets_to_player_and_roster_keys() -> None:
    document = build_search_document(TRADE_VERSION)

    assert "player:player-1" in document.entity_keys
    assert f"roster:{ROSTER_ID}" in document.entity_keys


def test_builder_uses_immutable_label_snapshot() -> None:
    document = build_search_document(STORYLINE_VERSION)

    assert "Old Sharks" in document.document_text
    assert document.entity_keys == (f"franchise:{FRANCHISE_ID}",)


def test_projection_hash_covers_output_driving_envelope_fields() -> None:
    original = build_search_document(FACT_VERSION)
    different_week = build_search_document(FACT_VERSION.model_copy(update={"week": 9}))
    different_season = build_search_document(
        FACT_VERSION.model_copy(update={"competition_season_id": OTHER_SEASON_ID})
    )

    assert original.content_hash != different_week.content_hash
    assert original.content_hash != different_season.content_hash
