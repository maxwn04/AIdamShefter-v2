import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.resources.memory.errors import InvalidMemoryContent
from backend.resources.memory.objects import (
    ContextNoteContent,
    ContextNoteIdentity,
    CreateItem,
    DEFAULT_EXPANSION,
    EventContent,
    FactContent,
    FranchiseKey,
    MemoryKind,
    MemoryMutationBundle,
    MemoryQuery,
    MemoryStatus,
    MutationItemResult,
    PlayerRef,
    EvidenceRef,
    StorylineContent,
    StandingsEventPayload,
    TriggerContent,
    TypedMemoryVersion,
    decode_memory_content,
)


ID_1 = UUID("00000000-0000-0000-0000-000000000001")
ID_2 = UUID("00000000-0000-0000-0000-000000000002")
ID_3 = UUID("00000000-0000-0000-0000-000000000003")
ID_4 = UUID("00000000-0000-0000-0000-000000000004")


@pytest.mark.parametrize(
    ("kind", "payload", "expected_type"),
    [
        (
            "storyline",
            {
                "headline": "The comeback",
                "summary": "A contender recovered from a slow start.",
                "status": "active",
                "salience": 4,
                "subjects": [
                    {
                        "kind": "player",
                        "id": "player-1",
                        "role": "focus",
                        "display_name": "A. Player",
                    }
                ],
            },
            StorylineContent,
        ),
        (
            "fact",
            {
                "claim": "The roster has won four straight.",
                "category": "streak",
                "confidence": "inferred",
                "status": "active",
                "subjects": [
                    {"kind": "franchise", "id": str(ID_1), "role": "subject"}
                ],
            },
            FactContent,
        ),
        (
            "event",
            {
                "event_type": "matchup",
                "headline": "An upset",
                "summary": "The underdog won.",
                "salience": 5,
                "confidence": "inferred",
                "status": "active",
                "details": {
                    "kind": "matchup",
                    "winner_franchise_id": str(ID_1),
                    "loser_franchise_id": str(ID_2),
                    "sleeper_matchup_id": "7",
                },
            },
            EventContent,
        ),
        (
            "trigger",
            {
                "trigger_type": "week",
                "status": "open",
                "fire_policy": "one_shot",
                "target_week": 9,
                "condition": {"kind": "week", "week": 9},
            },
            TriggerContent,
        ),
        (
            "context_note",
            {
                "narrative": "The league values running backs highly.",
                "status": "active",
                "tags": ["league culture"],
            },
            ContextNoteContent,
        ),
    ],
)
def test_decode_v1_content(
    kind: str,
    payload: dict[str, object],
    expected_type: type,
) -> None:
    decoded = decode_memory_content(kind, 1, payload)

    assert isinstance(decoded, expected_type)
    assert decoded.kind == kind
    assert decoded.schema_version == 1


def test_decode_rejects_unknown_schema_version_with_stable_error() -> None:
    with pytest.raises(InvalidMemoryContent) as error:
        decode_memory_content("fact", 2, {})

    assert error.value.code == "invalid_memory_content"
    assert error.value.details == {"kind": "fact", "schema_version": 2}


def test_decode_validation_details_are_transport_safe() -> None:
    with pytest.raises(InvalidMemoryContent) as error:
        decode_memory_content(
            "event",
            1,
            {
                "event_type": "matchup",
                "headline": "Impossible result",
                "summary": "One franchise cannot beat itself.",
                "salience": 3,
                "confidence": "inferred",
                "status": "active",
                "details": {
                    "kind": "matchup",
                    "winner_franchise_id": ID_1,
                    "loser_franchise_id": ID_1,
                    "sleeper_matchup_id": "7",
                },
            },
        )

    json.dumps(error.value.details)
    serialized_error = error.value.details["errors"][0]
    assert "input" not in serialized_error
    assert "ctx" not in serialized_error
    assert "url" not in serialized_error


def test_default_expansion_is_narrow_and_general() -> None:
    assert DEFAULT_EXPANSION.include_evidence is False
    assert DEFAULT_EXPANSION.include_related_items is False


def test_authored_content_is_deeply_immutable_and_serializes_as_json() -> None:
    input_numbers = {"streak": [1, {"wins": 3}]}
    fact = FactContent(
        claim="Three consecutive wins.",
        category="streak",
        confidence="inferred",
        status="active",
        numbers=input_numbers,
        subjects=[{"kind": "player", "id": "p1", "role": "subject"}],
    )
    input_numbers["streak"][1]["wins"] = 99

    assert fact.numbers["streak"][1]["wins"] == 3
    assert isinstance(fact.subjects, tuple)
    with pytest.raises(TypeError):
        fact.numbers["new"] = 1  # type: ignore[index]
    assert json.loads(fact.model_dump_json())["numbers"] == {
        "streak": [1, {"wins": 3}]
    }


def test_query_entities_are_role_free_keys() -> None:
    query = MemoryQuery(
        entities=[{"kind": "franchise", "id": ID_1}],
        kinds={"storyline"},
        statuses={"resolved"},
    )

    assert query.entities == (FranchiseKey(id=ID_1),)
    assert query.kinds == frozenset({MemoryKind.STORYLINE})
    assert query.statuses == frozenset({MemoryStatus.RESOLVED})
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        MemoryQuery(
            entities=[{"kind": "franchise", "id": ID_1, "role": "focus"}]
        )


def test_content_discriminators_and_owned_roles_are_validated() -> None:
    with pytest.raises(ValidationError, match="event_type must match details.kind"):
        EventContent.model_validate(
            {
                "event_type": "trade",
                "headline": "Mismatch",
                "summary": "Wrong payload.",
                "salience": 2,
                "confidence": "unverified",
                "status": "active",
                "details": {
                    "kind": "matchup",
                    "winner_franchise_id": str(ID_1),
                    "loser_franchise_id": str(ID_2),
                    "sleeper_matchup_id": "1",
                },
            }
        )

    with pytest.raises(ValidationError, match="invalid fact subject roles"):
        FactContent(
            claim="A claim",
            category="general",
            confidence="inferred",
            status="active",
            subjects=[PlayerRef(id="p1", role="focus")],
        )


def test_source_backed_fact_requires_and_accepts_typed_receipt() -> None:
    with pytest.raises(ValidationError, match="source-backed memory requires"):
        FactContent(
            claim="A sourced claim.",
            category="general",
            confidence="source_backed",
            status="active",
        )

    fact = FactContent(
        claim="A sourced claim.",
        category="general",
        confidence="source_backed",
        status="active",
        primary_tool_call_id=ID_1,
    )
    assert fact.primary_tool_call_id == ID_1


def test_source_backed_event_requires_and_accepts_typed_receipt() -> None:
    event_fields = {
        "event_type": "matchup",
        "headline": "A sourced result",
        "summary": "The favorite won.",
        "salience": 3,
        "confidence": "source_backed",
        "status": "active",
        "details": {
            "kind": "matchup",
            "winner_franchise_id": ID_1,
            "loser_franchise_id": ID_2,
            "sleeper_matchup_id": "5",
        },
    }
    with pytest.raises(ValidationError, match="source-backed memory requires"):
        EventContent.model_validate(event_fields)

    event = EventContent.model_validate(
        {**event_fields, "primary_api_request_id": ID_3}
    )
    assert event.primary_api_request_id == ID_3

def test_context_note_identity_enforces_scope_shape() -> None:
    ContextNoteIdentity(scope="competition", note_key="league-voice")

    with pytest.raises(ValidationError, match="target must match its scope"):
        ContextNoteIdentity(
            scope="franchise",
            note_key="team-outlook",
            competition_season_id=ID_1,
        )


def test_v1_standings_and_event_callback_shapes_are_typed() -> None:
    standings = StandingsEventPayload(
        franchise_id=ID_1,
        previous_rank=6,
        current_rank=3,
    )
    trigger = TriggerContent(
        trigger_type="event_callback",
        status="open",
        fire_policy="one_shot",
        target_competition_season_id=ID_2,
        condition={
            "kind": "event_callback",
            "event_type": "standings",
            "subject": {
                "kind": "franchise",
                "id": ID_1,
                "role": "subject",
            },
        },
    )

    assert standings.kind == "standings"
    assert trigger.condition.event_type == "standings"


def test_trigger_derives_redundant_storage_target_from_condition() -> None:
    trigger = TriggerContent(
        trigger_type="week",
        status="open",
        fire_policy="one_shot",
        condition={"kind": "week", "week": 0},
    )

    assert trigger.target_week == 0


def test_typed_version_requires_context_identity_exactly_for_context_notes() -> None:
    content = ContextNoteContent(
        narrative="A durable league convention.", status="active"
    )
    common = {
        "version_id": ID_1,
        "item_id": ID_2,
        "competition_id": ID_3,
        "kind": MemoryKind.CONTEXT_NOTE,
        "content": content,
        "content_schema_version": 1,
        "revision_number": 1,
        "introduced_revision_id": ID_4,
        "creating_generation_id": ID_1,
        "recorded_at": datetime(2026, 8, 9, tzinfo=UTC),
    }

    with pytest.raises(ValidationError, match="context_note_identity is required"):
        TypedMemoryVersion(**common)

    version = TypedMemoryVersion(
        **common,
        context_note_identity=ContextNoteIdentity(
            scope="competition", note_key="league-voice"
        ),
    )
    assert version.context_note_identity.note_key == "league-voice"


def test_mutation_bundle_derives_context_from_generation() -> None:
    bundle = MemoryMutationBundle(
        producing_generation_id=ID_1,
        operations=[
            CreateItem(
                client_key="fact:streak",
                content=FactContent(
                    claim="Four straight wins.",
                    category="streak",
                    confidence="inferred",
                    status="active",
                ),
            )
        ],
    )

    assert bundle.model_dump().keys() == {"producing_generation_id", "operations"}
    assert "expected_item_revision" not in bundle.model_dump_json()


def test_create_ids_support_same_bundle_references() -> None:
    fact = CreateItem(
        client_key="fact:streak",
        content=FactContent(
            claim="Four straight wins.",
            category="streak",
            confidence="inferred",
            status="active",
        ),
    )
    storyline = CreateItem(
        client_key="storyline:streak",
        content=StorylineContent(
            headline="The winning streak",
            summary="A run worth following.",
            status="active",
            salience=4,
            evidence=[
                EvidenceRef(
                    kind="fact",
                    version_id=fact.version_id,
                    role="origin",
                )
            ],
        ),
    )
    bundle = MemoryMutationBundle(
        producing_generation_id=ID_1,
        operations=(fact, storyline),
    )

    assert fact.item_id != fact.version_id
    assert bundle.operations[1].content.evidence[0].version_id == fact.version_id


def test_mutation_item_result_has_no_request_position() -> None:
    result = MutationItemResult(
        client_key="fact:streak",
        item_id=ID_1,
        version_id=ID_2,
    )

    assert result.model_dump() == {
        "client_key": "fact:streak",
        "item_id": ID_1,
        "version_id": ID_2,
    }
