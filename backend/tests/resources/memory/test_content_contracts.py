from uuid import uuid4

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from backend.resources.memory.context_notes import (
    ContextNoteContent,
    ContextNoteIdentity,
)
from backend.resources.memory.events import EventContent
from backend.resources.memory.facts import FactContent, FactEntityRef
from backend.resources.memory.storylines import EvidenceRef, StorylineContent
from backend.resources.memory.triggers import TriggerContent


def test_storyline_contract_normalizes_tags_and_validates_relationships() -> None:
    evidence_id = uuid4()
    storyline = StorylineContent.model_validate(
        {
            "headline": "  Deadline fallout  ",
            "summary": "A contender paid up to complete its roster.",
            "status": "active",
            "salience": 4,
            "tags": [" Trade ", "trade", "  "],
            "subjects": [
                {"kind": "franchise", "id": uuid4(), "role": "focus"},
                {"kind": "player", "id": "player-1", "role": "counterparty"},
            ],
            "evidence": [
                {"kind": "fact", "version_id": evidence_id, "role": "support"}
            ],
            "related_storylines": [
                {"item_id": uuid4(), "role": "continuation"}
            ],
        }
    )

    assert storyline.headline == "Deadline fallout"
    assert storyline.tags == ["trade"]
    assert storyline.evidence[0].kind == "fact"

    with pytest.raises(ValidationError, match="evidence versions must be distinct"):
        StorylineContent.model_validate(
            {
                **storyline.model_dump(),
                "evidence": [
                    {"kind": "fact", "version_id": evidence_id, "role": "support"},
                    {"kind": "fact", "version_id": evidence_id, "role": "update"},
                ],
            }
        )

    with pytest.raises(ValidationError, match="requires a focus"):
        StorylineContent.model_validate(
            {
                **storyline.model_dump(),
                "subjects": [
                    {
                        "kind": "player",
                        "id": "player-1",
                        "role": "counterparty",
                    }
                ],
            }
        )


def test_fact_entity_reference_has_a_resource_local_role() -> None:
    reference = TypeAdapter(FactEntityRef).validate_python(
        {"kind": "player", "id": "player-1", "role": "subject"}
    )
    assert reference.role == "subject"

    with pytest.raises(ValidationError):
        TypeAdapter(FactEntityRef).validate_python(
            {"kind": "player", "id": "player-1", "role": "focus"}
        )


@pytest.mark.parametrize("kind", ["fact", "event"])
def test_storyline_evidence_discriminator_covers_exact_reference_kinds(
    kind: str,
) -> None:
    reference = TypeAdapter(EvidenceRef).validate_python(
        {"kind": kind, "version_id": uuid4(), "role": "support"}
    )
    assert reference.kind == kind


def test_fact_contract_requires_typed_receipt_for_source_backed_claim() -> None:
    fact = FactContent(
        claim="The franchise won six straight games.",
        category="streak",
        numbers={"wins": 6},
        confidence="source_backed",
        status="active",
        subjects=[],
        originating_event_version_ids=[],
        primary_api_request_id=uuid4(),
    )
    assert fact.numbers == {"wins": 6}

    with pytest.raises(ValidationError, match="typed primary receipt"):
        FactContent.model_validate(
            {
                **fact.model_dump(),
                "primary_api_request_id": None,
                "source_hints": {"note": "remembered from last week"},
            }
        )

    with pytest.raises(ValidationError, match="finite number"):
        FactContent.model_validate(
            {
                **fact.model_dump(),
                "confidence": "unverified",
                "numbers": {"invalid": float("nan")},
            }
        )


@pytest.mark.parametrize(
    "identity",
    [
        {"scope": "competition", "note_key": "league_voice"},
        {
            "scope": "competition_season",
            "competition_season_id": uuid4(),
            "note_key": "playoff_race",
        },
        {"scope": "franchise", "franchise_id": uuid4(), "note_key": "outlook"},
    ],
)
def test_context_note_identity_discriminator(identity: dict[str, object]) -> None:
    parsed = TypeAdapter(ContextNoteIdentity).validate_python(identity)
    assert parsed.scope == identity["scope"]


def test_context_note_identity_rejects_mixed_scope_shape() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(ContextNoteIdentity).validate_python(
            {
                "scope": "competition",
                "franchise_id": uuid4(),
                "note_key": "outlook",
            }
        )


@pytest.mark.parametrize(
    ("contract", "payload"),
    [
        (
            StorylineContent,
            {
                "headline": "h",
                "summary": "s",
                "status": "active",
                "salience": 1,
                "tags": [],
                "subjects": [],
                "evidence": [],
                "related_storylines": [],
            },
        ),
        (
            FactContent,
            {
                "claim": "c",
                "category": "cat",
                "numbers": {},
                "confidence": "unverified",
                "status": "active",
                "subjects": [],
                "originating_event_version_ids": [],
            },
        ),
        (
            EventContent,
            {
                "event_type": "matchup",
                "headline": "h",
                "summary": "s",
                "salience": 1,
                "confidence": "unverified",
                "status": "active",
                "details": {
                    "kind": "matchup",
                    "winner_franchise_id": uuid4(),
                    "loser_franchise_id": uuid4(),
                    "sleeper_matchup_id": "1",
                },
            },
        ),
        (
            TriggerContent,
            {
                "trigger_type": "rematch",
                "status": "open",
                "fire_policy": "one_shot",
                "target_competition_season_id": uuid4(),
                "target_week": 1,
                "condition": {
                    "kind": "rematch",
                    "franchise_ids": [uuid4(), uuid4()],
                },
            },
        ),
        (
            ContextNoteContent,
            {"narrative": "n", "status": "active", "tags": []},
        ),
    ],
)
def test_current_resource_schema_decodes_and_unknown_versions_are_rejected(
    contract: type[BaseModel],
    payload: dict[str, object],
) -> None:
    current = contract.model_validate(payload)
    assert current.schema_version == 1
    assert contract.model_validate_json(current.model_dump_json()) == current

    with pytest.raises(ValidationError):
        contract.model_validate({**payload, "schema_version": 2})
