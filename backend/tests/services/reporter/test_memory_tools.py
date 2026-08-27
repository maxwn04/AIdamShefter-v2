"""Tests for the legacy-shaped buffered memory adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from backend.resources.memory.common.versioning import (
    MemoryItemIdentity,
    MemoryVersionMetadata,
)
from backend.resources.memory.events import Event, EventContent
from backend.resources.memory.search_documents import (
    SearchMatchReason,
    SearchScoreComponents,
)
from backend.services.datalayer import (
    FrozenRosterIdentity,
    ResolvedRosterIdentity,
    RosterIdentityNotFound,
)
from backend.services.memory import (
    GenerationMemoryContext,
    HydratedMemoryMatch,
    MemoryKind,
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
)
from backend.services.reporter.runner.run_log import RunLog
from backend.services.reporter.runner.state import ArtifactStore, ProcedureState
from backend.services.reporter.runner.tools.context import ToolContext
from backend.services.reporter.runner.tools.memory_tools import (
    MEMORY_TOOL_IMPLEMENTATION_VERSION,
    MEMORY_TOOL_SPECS,
    TypedMemoryAdapter,
    register_memory_tools,
)
from backend.services.reporter.runner.tools.registry import ToolRegistry


COMPETITION_ID = UUID(int=1)
SEASON_ID = UUID(int=2)
TACO_ROSTER_ID = UUID(int=3)
TACO_FRANCHISE_ID = UUID(int=4)
WIRE_ROSTER_ID = UUID(int=5)
WIRE_FRANCHISE_ID = UUID(int=6)
NOW = datetime(2026, 8, 26, tzinfo=UTC)


class RecordingRetrieval:
    def __init__(self, matches: tuple[HydratedMemoryMatch, ...] = ()) -> None:
        self.calls: list[MemoryRetrievalRequest] = []
        self.matches = matches

    def search(
        self,
        *,
        competition_id: UUID,
        revision_id: UUID,
        request: MemoryRetrievalRequest,
    ) -> MemoryRetrievalResult:
        self.calls.append(request)
        return MemoryRetrievalResult(
            competition_id=competition_id,
            revision_id=revision_id,
            matches=self.matches,
        )


class FrozenData:
    def __init__(self) -> None:
        self.identities = {
            "Team Taco": FrozenRosterIdentity(
                competition_id=COMPETITION_ID,
                competition_season_id=SEASON_ID,
                season_roster_id=TACO_ROSTER_ID,
                franchise_id=TACO_FRANCHISE_ID,
                sleeper_roster_id="1",
                team_name="Team Taco",
                manager_name="Alice",
            ),
            "Waiver Wire": FrozenRosterIdentity(
                competition_id=COMPETITION_ID,
                competition_season_id=SEASON_ID,
                season_roster_id=WIRE_ROSTER_ID,
                franchise_id=WIRE_FRANCHISE_ID,
                sleeper_roster_id="2",
                team_name="Waiver Wire",
                manager_name="Bob",
            ),
        }

    def resolve_roster_identity(self, roster_key: str) -> Any:
        identity = self.identities.get(roster_key)
        if identity is None:
            return RosterIdentityNotFound(roster_key=roster_key)
        return ResolvedRosterIdentity(roster_key=roster_key, identity=identity)


def _registered(
    *,
    matches: tuple[HydratedMemoryMatch, ...] = (),
    allow_memory_writes: bool = True,
) -> tuple[
    ToolRegistry,
    ToolContext,
    GenerationMemoryContext,
    RecordingRetrieval,
    TypedMemoryAdapter,
]:
    retrieval = RecordingRetrieval(matches)
    memory = GenerationMemoryContext(
        competition_id=COMPETITION_ID,
        generation_id=uuid4(),
        pinned_revision_id=uuid4(),
        retrieval=retrieval,
        competition_season_id=SEASON_ID,
        week=8,
    )
    registry = ToolRegistry()
    adapter = register_memory_tools(
        registry,
        memory,
        FrozenData(),  # type: ignore[arg-type]
        allow_memory_writes=allow_memory_writes,
    )
    context = ToolContext(
        artifacts=ArtifactStore(),
        procedures=ProcedureState(),
        log=RunLog(session_id="memory-tools"),
    )
    registry.set_context(context)
    return registry, context, memory, retrieval, adapter


def _call(registry: ToolRegistry, name: str, **arguments: Any) -> dict[str, Any]:
    handler = registry.get_handler(name)
    assert handler is not None
    result = handler(**arguments)
    assert isinstance(result, dict)
    return result


def _event_args(*, event_id: str = "event_week8") -> dict[str, Any]:
    return {
        "id": event_id,
        "event_type": "matchup",
        "week": 3,
        "headline": "Taco won the Week 8 matchup.",
        "summary": "Team Taco defeated Waiver Wire.",
        "importance": 4,
        "confidence": "verified",
        "source_refs": ["team_game:week8:taco"],
        "numbers": {"week": 8},
        "matchup_id": "week-8-1",
        "details": {
            "kind": "matchup",
            "winner_roster_key": "Team Taco",
            "loser_roster_key": "Waiver Wire",
            "sleeper_matchup_id": "week-8-1",
        },
    }


def _note() -> dict[str, Any]:
    return {
        "roster_key": "Team Taco",
        "narrative": "Team Taco is surging toward the playoffs.",
        "outlook": "surging",
    }


def _seed_brief(context: ToolContext) -> None:
    fact = context.brief.prepare_fact(
        id="taco_week8_win",
        claim_text="Team Taco won in Week 8.",
        data_refs=["team_game:week8:taco"],
        numbers={"week": 8},
        category="matchup_result",
    )
    context.brief.commit(fact, lambda _: None)
    storyline = context.brief.prepare_storyline(
        id="taco_playoff_push",
        headline="Taco's push is getting louder.",
        summary="The Week 8 win strengthened the contender arc.",
        supporting_fact_ids=["taco_week8_win"],
        priority=4,
        tags=["playoffs"],
    )
    context.brief.commit(storyline, lambda _: None)


def _event_match() -> HydratedMemoryMatch:
    event = Event(
        item=MemoryItemIdentity(
            item_id=UUID(int=20),
            competition_id=COMPETITION_ID,
            kind=MemoryKind.EVENT,
            agent_key="event_week8",
            created_at=NOW,
        ),
        version=MemoryVersionMetadata(
            version_id=UUID(int=21),
            revision_number=7,
            content_schema_version=1,
            introduced_revision_id=UUID(int=22),
            creating_generation_id=UUID(int=23),
            recorded_at=NOW,
        ),
        content=EventContent.model_validate(
            {
                "event_type": "matchup",
                "headline": "Taco won the Week 8 matchup.",
                "summary": "An older summary.",
                "salience": 4,
                "confidence": "inferred",
                "status": "active",
                "details": {
                    "kind": "matchup",
                    "winner_franchise_id": TACO_FRANCHISE_ID,
                    "loser_franchise_id": WIRE_FRANCHISE_ID,
                    "sleeper_matchup_id": "week-8-1",
                },
                "source_hints": {},
            }
        ),
    )
    return HydratedMemoryMatch(
        memory=event,
        score=1,
        score_components=SearchScoreComponents(lexical_rank=1),
        match_reasons=(SearchMatchReason.LEXICAL_MATCH,),
    )


def test_registers_legacy_semantic_surface() -> None:
    registry, _, _, _, _ = _registered()
    assert registry.tool_names == [
        "search_memory",
        "save_memory_event",
        "upsert_storyline_memory_card",
        "save_storyline_trigger",
        "save_team_context",
        "save_league_note",
    ]
    assert registry.tool_specs == MEMORY_TOOL_SPECS
    assert registry.tool_implementation_versions == [
        (name, MEMORY_TOOL_IMPLEMENTATION_VERSION) for name in registry.tool_names
    ]


def test_search_remains_pinned_and_resolves_team_keys() -> None:
    registry, _, memory, retrieval, _ = _registered()
    result = _call(registry, "search_memory", text="push", team_keys=["Team Taco"])
    assert result["revision_id"] == str(memory.pinned_revision_id)
    assert retrieval.calls[0].query.entity_keys == (
        f"franchise:{TACO_FRANCHISE_ID}",
        f"season_roster:{TACO_ROSTER_ID}",
    )


def test_legacy_writes_buffer_typed_proposals() -> None:
    registry, _, memory, _, _ = _registered()
    event = _call(registry, "save_memory_event", **_event_args())
    card = _call(
        registry,
        "upsert_storyline_memory_card",
        id="story_taco",
        headline="Taco Takes Control",
        summary="The playoff push is real.",
        status="active",
        priority=4,
        origin_week=3,
        team_keys=["Team Taco"],
        evidence_event_ids=["event_week8"],
    )
    trigger = _call(
        registry,
        "save_storyline_trigger",
        id="trigger_rematch",
        storyline_id="story_taco",
        trigger_type="rematch",
        target_week=12,
        condition={"roster_keys": ["Team Taco", "Waiver Wire"]},
    )
    team = _call(registry, "save_team_context", **_note())
    league = _call(
        registry,
        "save_league_note",
        key="playoff_race",
        value="The top seed remains unsettled.",
    )
    assert all(item["ok"] for item in (event, card, trigger, team, league))
    assert card["team_ids"] == [1]
    assert team["roster_id"] == 1
    bundle = memory.take_completed_bundle()
    assert [item.kind for item in bundle.proposals] == [
        MemoryKind.EVENT,
        MemoryKind.STORYLINE,
        MemoryKind.TRIGGER,
        MemoryKind.CONTEXT_NOTE,
        MemoryKind.CONTEXT_NOTE,
    ]
    assert [item.metadata.agent_key for item in bundle.proposals] == [
        "event_week8",
        "story_taco",
        "trigger_rematch",
        f"team_context:{TACO_FRANCHISE_ID}",
        "league_note:playoff_race",
    ]
    assert bundle.proposals[0].content.source_hints["week"] == 3
    assert bundle.proposals[0].content.source_hints["importance"] == 4
    assert bundle.proposals[0].metadata.week == 3
    assert bundle.proposals[1].content.salience == 2
    assert bundle.proposals[1].metadata.week == 3


def test_stable_id_resolves_internal_replace_revision() -> None:
    match = _event_match()
    registry, _, memory, _, _ = _registered(matches=(match,))
    result = _call(registry, "save_memory_event", **_event_args())
    assert result["saved"] is True
    proposal = memory.take_completed_bundle().proposals[0]
    assert proposal.operation == "replace"
    assert proposal.item_id == match.memory.item.item_id
    assert proposal.expected_item_revision == 7


def test_post_submit_bridge_buffers_only_supporting_facts_idempotently() -> None:
    _, context, memory, _, adapter = _registered()
    _seed_brief(context)
    first = adapter.buffer_brief_facts(context.brief.brief)
    repeated = adapter.buffer_brief_facts(context.brief.brief)
    assert first[0]["saved"] is True
    assert repeated[0]["saved"] is False
    bundle = memory.take_completed_bundle()
    assert len(bundle.proposals) == 1
    proposal = bundle.proposals[0]
    assert proposal.kind is MemoryKind.FACT
    assert proposal.metadata.agent_key == (
        "brief:taco_playoff_push:8:taco_week8_win"
    )
    assert proposal.content.source_hints["brief_storyline_id"] == "taco_playoff_push"


def test_eval_mode_keeps_search_and_skips_legacy_writes() -> None:
    registry, _, memory, retrieval, _ = _registered(allow_memory_writes=False)
    searched = _call(registry, "search_memory", text="Taco")
    blocked = _call(registry, "save_memory_event", **_event_args())
    assert searched["ok"] is True
    assert blocked["saved"] is False
    assert blocked["eval_mode"] is True
    assert blocked["recorded"] is False
    assert len(retrieval.calls) == 1
    assert memory.take_completed_bundle().proposals == ()


def test_invalid_legacy_inputs_are_safe_and_do_not_buffer() -> None:
    registry, _, memory, _, _ = _registered()
    missing_source = _event_args()
    missing_source["source_refs"] = []
    verified = _call(registry, "save_memory_event", **missing_source)
    missing_details = _event_args()
    missing_details.pop("details")
    details = _call(registry, "save_memory_event", **missing_details)
    unresolved = _call(
        registry,
        "save_team_context",
        roster_key="missing",
        narrative="Unknown team.",
    )
    assert verified["error"]["code"] == "missing_source_refs"
    assert verified["saved"] is False
    assert details["error"]["code"] == "missing_event_details"
    assert details["saved"] is False
    assert unresolved["error"]["code"] == "roster_not_found"
    assert unresolved["saved"] is False
    assert memory.take_completed_bundle().proposals == ()
