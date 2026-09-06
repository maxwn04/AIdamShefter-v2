from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from backend.resources.memory.common.versioning import (
    MemoryItemIdentity,
    MemoryVersionMetadata,
)
from backend.resources.memory.context_notes import ContextNote, ContextNoteContent
from backend.resources.memory.events import Event, EventContent
from backend.resources.memory.facts import Fact, FactContent
from backend.resources.memory.search_documents import (
    SearchDocumentQuery,
    SearchMatchReason,
    SearchScoreComponents,
)
from backend.resources.memory.storylines import Storyline, StorylineContent
from backend.resources.memory.triggers import Trigger, TriggerContent
from backend.services.datalayer import FrozenRosterIdentity
from backend.services.memory import (
    HydratedMemoryMatch,
    MemoryKind,
    MemoryRetrievalResult,
    RelatedStorylineExpansion,
    StorylineEvidenceExpansion,
    TriggerTargetStorylineExpansion,
)
from backend.services.reporter.runner.models import ToolExecutionResult
from backend.services.reporter.runner.tools.memory_presentation import (
    MAX_PRESENTED_REFERENCES,
    MemoryPresentationAdapter,
)


COMPETITION_ID = UUID(int=1)
SEASON_ID = UUID(int=2)
TACO_ROSTER_ID = UUID(int=3)
TACO_FRANCHISE_ID = UUID(int=4)
WIRE_ROSTER_ID = UUID(int=5)
WIRE_FRANCHISE_ID = UUID(int=6)
NOW = datetime(2026, 8, 29, tzinfo=UTC)


class FrozenData:
    identities = (
        FrozenRosterIdentity(
            competition_id=COMPETITION_ID,
            competition_season_id=SEASON_ID,
            season_roster_id=TACO_ROSTER_ID,
            franchise_id=TACO_FRANCHISE_ID,
            sleeper_roster_id="1",
            team_name="Team Taco",
            manager_name="Alice",
        ),
        FrozenRosterIdentity(
            competition_id=COMPETITION_ID,
            competition_season_id=SEASON_ID,
            season_roster_id=WIRE_ROSTER_ID,
            franchise_id=WIRE_FRANCHISE_ID,
            sleeper_roster_id="2",
            team_name="Waiver Wire",
            manager_name="Bob",
        ),
    )

    def get_roster_identity_by_canonical_id(
        self,
        *,
        franchise_id: UUID | None = None,
        season_roster_id: UUID | None = None,
    ) -> FrozenRosterIdentity | None:
        return next(
            (
                identity
                for identity in self.identities
                if identity.franchise_id == franchise_id
                or identity.season_roster_id == season_roster_id
            ),
            None,
        )

    def get_player_summary(self, player_key: Any) -> dict[str, Any]:
        if player_key == "player-1":
            return {"found": True, "player": {"player_name": "Breece Hall"}}
        return {"found": False, "player_key": player_key}


def _identity(kind: MemoryKind, number: int, *, agent_key: str) -> MemoryItemIdentity:
    return MemoryItemIdentity(
        item_id=UUID(int=number),
        competition_id=COMPETITION_ID,
        kind=kind,
        agent_key=agent_key,
        created_at=NOW,
    )


def _version(number: int, revision: int = 1) -> MemoryVersionMetadata:
    return MemoryVersionMetadata(
        version_id=UUID(int=number),
        revision_number=revision,
        content_schema_version=1,
        introduced_revision_id=UUID(int=number + 100),
        creating_generation_id=UUID(int=number + 200),
        recorded_at=NOW,
    )


def _event() -> Event:
    return Event(
        item=_identity(MemoryKind.EVENT, 10, agent_key="event-week-8"),
        version=_version(11, 2),
        content=EventContent.model_validate(
            {
                "event_type": "trade",
                "headline": "Taco bought another star",
                "summary": "Taco sent FAAB and a pick for Breece Hall.",
                "salience": 5,
                "confidence": "inferred",
                "status": "active",
                "details": {
                    "kind": "trade",
                    "sender_franchise_id": TACO_FRANCHISE_ID,
                    "receiver_franchise_id": WIRE_FRANCHISE_ID,
                    "assets": [
                        {
                            "kind": "player",
                            "direction": "receiver_to_sender",
                            "player_id": "player-1",
                        },
                        {
                            "kind": "draft_pick",
                            "direction": "sender_to_receiver",
                            "draft_pick_id": UUID(int=99),
                        },
                        {
                            "kind": "budget",
                            "direction": "sender_to_receiver",
                            "amount": 17,
                        },
                    ],
                },
                "source_hints": {"private": "diagnostic"},
            }
        ),
    )


def _fact(event: Event) -> Fact:
    return Fact(
        item=_identity(MemoryKind.FACT, 20, agent_key="fact-week-8"),
        version=_version(21, 3),
        content=FactContent.model_validate(
            {
                "claim": "Team Taco has won three straight.",
                "category": "streak",
                "numbers": {"wins": 3},
                "confidence": "inferred",
                "status": "active",
                "subjects": [
                    {
                        "kind": "franchise",
                        "id": TACO_FRANCHISE_ID,
                        "role": "subject",
                    }
                ],
                "originating_event_version_ids": [event.version.version_id],
                "source_hints": {"private": "diagnostic"},
            }
        ),
    )


def _related_storyline() -> Storyline:
    return Storyline(
        item=_identity(MemoryKind.STORYLINE, 30, agent_key="related-arc"),
        version=_version(31),
        content=StorylineContent.model_validate(
            {
                "headline": "The old contender arc",
                "summary": "Taco entered the season as a favorite.",
                "status": "dormant",
                "arc_type": "contender",
                "salience": 3,
                "tags": ["playoffs"],
                "subjects": [],
                "evidence": [],
                "related_storylines": [],
            }
        ),
    )


def _storyline(fact: Fact, related: Storyline) -> Storyline:
    return Storyline(
        item=_identity(MemoryKind.STORYLINE, 40, agent_key="taco-push"),
        version=_version(41, 4),
        content=StorylineContent.model_validate(
            {
                "headline": "Taco's push is getting louder",
                "summary": "Three wins changed the playoff stakes.",
                "status": "active",
                "arc_type": "playoff_push",
                "salience": 5,
                "tags": ["playoffs", "streak"],
                "subjects": [
                    {
                        "kind": "franchise",
                        "id": TACO_FRANCHISE_ID,
                        "role": "focus",
                    }
                ],
                "evidence": [
                    {
                        "kind": "fact",
                        "version_id": fact.version.version_id,
                        "role": "support",
                    }
                ],
                "related_storylines": [
                    {
                        "item_id": related.item.item_id,
                        "role": "continuation",
                    }
                ],
                "callback_condition": "Revisit after Taco loses.",
            }
        ),
    )


def _trigger(storyline: Storyline) -> Trigger:
    return Trigger(
        item=_identity(MemoryKind.TRIGGER, 50, agent_key="taco-rematch"),
        version=_version(51),
        content=TriggerContent.model_validate(
            {
                "trigger_type": "rematch",
                "status": "open",
                "fire_policy": "one_shot",
                "target_competition_season_id": SEASON_ID,
                "target_storyline_item_id": storyline.item.item_id,
                "target_week": 12,
                "condition": {
                    "kind": "rematch",
                    "franchise_ids": [TACO_FRANCHISE_ID, WIRE_FRANCHISE_ID],
                },
            }
        ),
    )


def _context_note() -> ContextNote:
    return ContextNote(
        item=_identity(MemoryKind.CONTEXT_NOTE, 60, agent_key="team-context"),
        version=_version(61),
        note_identity={
            "scope": "franchise",
            "franchise_id": TACO_FRANCHISE_ID,
            "note_key": "direction",
        },
        content=ContextNoteContent.model_validate(
            {
                "narrative": "Taco is operating like a contender.",
                "outlook": "surging",
                "status": "active",
                "tags": ["identity"],
            }
        ),
    )


def _match(memory: Any, *, week: int | None = None, **kwargs: Any) -> HydratedMemoryMatch:
    return HydratedMemoryMatch(
        memory=memory,
        week=week,
        score=2.5,
        score_components=SearchScoreComponents(lexical_rank=2, salience=0.5),
        match_reasons=(SearchMatchReason.LEXICAL_MATCH,),
        matched_entity_keys=(f"franchise:{TACO_FRANCHISE_ID}",),
        **kwargs,
    )


def _present(matches: tuple[HydratedMemoryMatch, ...], *, limit: int = 8) -> ToolExecutionResult:
    return MemoryPresentationAdapter(FrozenData()).present(  # type: ignore[arg-type]
        MemoryRetrievalResult(
            competition_id=COMPETITION_ID,
            revision_id=UUID(int=500),
            matches=matches,
        ),
        query=SearchDocumentQuery(text="playoff push", limit=limit + 1),
        limit=limit,
    )


def _assert_forbidden_fields_absent(value: Any) -> None:
    forbidden = {
        "id",
        "item_id",
        "version_id",
        "revision_id",
        "revision_number",
        "competition_id",
        "competition_season_id",
        "created_at",
        "recorded_at",
        "content_hash",
        "score",
        "score_components",
        "matched_entity_keys",
        "matched_evidence_version_ids",
        "matched_related_item_ids",
        "match_reasons",
        "source_hints",
        "primary_tool_call_id",
        "primary_api_request_id",
    }
    if isinstance(value, dict):
        assert forbidden.isdisjoint(value)
        for child in value.values():
            _assert_forbidden_fields_absent(child)
    elif isinstance(value, list):
        for child in value:
            _assert_forbidden_fields_absent(child)


def test_projects_every_memory_kind_without_canonical_fields() -> None:
    event = _event()
    fact = _fact(event)
    related = _related_storyline()
    storyline = _storyline(fact, related)
    trigger = _trigger(storyline)
    note = _context_note()
    execution = _present(
        (
            _match(
                storyline,
                week=8,
                exact_references=(
                    StorylineEvidenceExpansion(
                        reference=storyline.content.evidence[0],
                        memory=fact,
                    ),
                ),
                stable_references=(
                    RelatedStorylineExpansion(
                        reference=storyline.content.related_storylines[0],
                        memory=related,
                    ),
                ),
            ),
            _match(fact, week=8),
            _match(event, week=8),
            _match(
                trigger,
                stable_references=(
                    TriggerTargetStorylineExpansion(
                        item_id=storyline.item.item_id,
                        memory=storyline,
                    ),
                ),
            ),
            _match(note),
        )
    )

    result = execution.result
    assert isinstance(result, dict)
    assert [memory["kind"] for memory in result["memories"]] == [
        "storyline",
        "fact",
        "event",
        "trigger",
        "context_note",
    ]
    storyline_result, fact_result, event_result, trigger_result, note_result = (
        result["memories"]
    )
    assert storyline_result["subjects"] == [
        {"label": "Team Taco", "role": "focus", "team_key": f"franchise:{TACO_FRANCHISE_ID}"}
    ]
    assert storyline_result["evidence"][0]["summary"] == fact.content.claim
    assert storyline_result["related_memories"][0]["headline"] == (
        related.content.headline
    )
    assert fact_result["numbers"] == {"wins": 3}
    assert event_result["participants"] == [
        {"label": "Team Taco", "role": "sender", "team_key": f"franchise:{TACO_FRANCHISE_ID}"},
        {"label": "Waiver Wire", "role": "receiver", "team_key": f"franchise:{WIRE_FRANCHISE_ID}"},
    ]
    assert event_result["assets"] == [
        {"label": "Breece Hall", "direction": "receiver_to_sender"},
        {"label": "Draft pick", "direction": "sender_to_receiver"},
        {"label": "17 FAAB", "direction": "sender_to_receiver"},
    ]
    assert trigger_result["condition_summary"] == (
        "Check whether there is a rematch between Team Taco and Waiver Wire"
    )
    assert trigger_result["linked_memories"][0]["headline"] == (
        storyline.content.headline
    )
    assert note_result["scope_label"] == "Team Taco"
    _assert_forbidden_fields_absent(result)

    bindings = execution.metadata["bindings"]
    assert isinstance(bindings, list)
    assert len(bindings) == 8
    assert {tuple(binding["result_path"]) for binding in bindings} == {
        ("memories", 0),
        ("memories", 0, "evidence", 0),
        ("memories", 0, "related_memories", 0),
        ("memories", 1),
        ("memories", 2),
        ("memories", 3),
        ("memories", 3, "linked_memories", 0),
        ("memories", 4),
    }
    assert bindings[0]["item_id"] == str(storyline.item.item_id)
    assert bindings[0]["expected_item_revision"] == 4
    assert "franchise:" in bindings[0]["matched_entity_keys"][0]


def test_bounds_nested_references_and_records_omissions() -> None:
    event = _event()
    fact = _fact(event)
    related = _related_storyline()
    storyline = _storyline(fact, related)
    expansion = StorylineEvidenceExpansion(
        reference=storyline.content.evidence[0],
        memory=fact,
    )
    execution = _present(
        (
            _match(
                storyline,
                exact_references=(expansion,) * (MAX_PRESENTED_REFERENCES + 1),
            ),
            _match(fact),
        ),
        limit=1,
    )
    result = execution.result
    assert isinstance(result, dict)
    assert len(result["memories"][0]["evidence"]) == MAX_PRESENTED_REFERENCES
    assert result["truncated"] is True
    assert execution.metadata["retrieved_count"] == 2
    assert execution.metadata["returned_count"] == 1
    assert execution.metadata["omitted_count"] == 2


def test_missing_labels_use_neutral_text_and_hidden_diagnostics() -> None:
    fact = Fact(
        item=_identity(MemoryKind.FACT, 70, agent_key="unknown-player"),
        version=_version(71),
        content=FactContent.model_validate(
            {
                "claim": "An unknown player changed the matchup.",
                "category": "player",
                "numbers": {},
                "confidence": "inferred",
                "status": "active",
                "subjects": [
                    {
                        "kind": "player",
                        "id": "private-player-id",
                        "role": "subject",
                    }
                ],
                "originating_event_version_ids": [],
                "source_hints": {},
            }
        ),
    )
    execution = _present((_match(fact),))
    result = execution.result
    assert isinstance(result, dict)
    assert result["memories"][0]["subjects"] == [
        {"label": "Player", "role": "subject"}
    ]
    assert "private-player-id" not in str(result)
    bindings = execution.metadata["bindings"]
    assert isinstance(bindings, list)
    assert bindings[0]["omitted_fields"] == ["subjects.0.label"]


def test_empty_result_has_bounded_notice() -> None:
    execution = _present(())
    assert execution.result == {
        "memories": [],
        "notice": "No relevant memory matched these editorial selectors."
        " Text matching is lexical. Try a short name or concept, or omit text "
        "and browse with team, kind, or status filters; then inspect selected matches.",
        "truncated": False,
    }
    assert execution.metadata["bindings"] == []
