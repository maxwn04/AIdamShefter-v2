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
from backend.services.reporter.runner.models import ToolExecutionResult
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

    def get_roster_identity_by_canonical_id(
        self,
        *,
        franchise_id: UUID | None = None,
        season_roster_id: UUID | None = None,
    ) -> FrozenRosterIdentity | None:
        return next(
            (
                identity
                for identity in self.identities.values()
                if identity.franchise_id == franchise_id
                or identity.season_roster_id == season_roster_id
            ),
            None,
        )

    def get_player_summary(self, player_key: Any) -> dict[str, Any]:
        return {"found": False, "player_key": player_key}


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


def _execution_call(
    registry: ToolRegistry, name: str, **arguments: Any
) -> ToolExecutionResult | dict[str, Any]:
    handler = registry.get_handler(name)
    assert handler is not None
    result = handler(**arguments)
    assert isinstance(result, (ToolExecutionResult, dict))
    return result


def _call(registry: ToolRegistry, name: str, **arguments: Any) -> dict[str, Any]:
    execution = _execution_call(registry, name, **arguments)
    result = execution.result if isinstance(execution, ToolExecutionResult) else execution
    assert isinstance(result, dict)
    return result


def _search_call(
    registry: ToolRegistry,
    **arguments: Any,
) -> ToolExecutionResult | dict[str, Any]:
    handler = registry.get_handler("search_memory")
    assert handler is not None
    result = handler(**arguments)
    assert isinstance(result, (ToolExecutionResult, dict))
    return result


def _event_args(*, event_id: str = "event_week8") -> dict[str, Any]:
    return {
        "id": event_id,
        "event_type": "matchup",
        "source_fact_ids": ["fact_event"],
        "headline": "Taco won the Week 8 matchup.",
        "summary": "Team Taco defeated Waiver Wire.",
        "importance": 4,
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


def test_registers_semantic_memory_surface() -> None:
    registry, _, _, _, _ = _registered()
    assert registry.tool_names == [
        "search_memory",
        "inspect_memory",
        "save_memory_event",
        "upsert_storyline_memory_card",
        "save_storyline_trigger",
        "update_memory_callback",
        "save_team_context",
        "save_league_note",
    ]
    assert registry.tool_specs == MEMORY_TOOL_SPECS
    assert registry.tool_implementation_versions == [
        (name, MEMORY_TOOL_IMPLEMENTATION_VERSION) for name in registry.tool_names
    ]


def test_search_schema_exposes_only_editorial_selectors() -> None:
    search = next(
        spec["function"]
        for spec in MEMORY_TOOL_SPECS
        if spec["function"]["name"] == "search_memory"
    )
    description = search["description"]
    properties = search["parameters"]["properties"]

    assert MEMORY_TOOL_IMPLEMENTATION_VERSION == "9"
    assert "editorial intent" in description
    assert "storage identifiers" in description
    assert set(properties) == {
        "text",
        "season",
        "team_keys",
        "tags",
        "kinds",
        "statuses",
        "week_from",
        "week_to",
        "limit",
        "include_evidence",
        "include_related",
    }
    assert properties["limit"]["default"] == 8
    assert properties["limit"]["maximum"] == 25
    assert properties["include_evidence"]["default"] is False
    assert properties["include_related"]["default"] is False


def test_search_remains_pinned_and_resolves_team_keys() -> None:
    registry, _, memory, retrieval, _ = _registered()
    execution = _search_call(
        registry,
        text="push",
        team_keys=["Team Taco"],
    )
    assert isinstance(execution, ToolExecutionResult)
    assert execution.result["memories"] == []
    assert "miss does not establish" in execution.result["notice"]
    assert execution.result["retrieval_status"]["status"] == "disabled"
    assert execution.result["truncated"] is False
    assert retrieval.calls[0].query.include_history
    assert execution.metadata["pinned_revision_id"] == str(
        memory.pinned_revision_id
    )
    assert retrieval.calls[0].query.required_entity_keys == (
        f"franchise:{TACO_FRANCHISE_ID}",
        f"roster:{TACO_ROSTER_ID}",
    )
    assert retrieval.calls[0].query.competition_season_id is None
    assert retrieval.calls[0].query.limit == 9
    assert retrieval.calls[0].expand_exact_references is False
    assert retrieval.calls[0].expand_stable_references is False


def test_search_rejects_identifier_inputs_and_reversed_ranges() -> None:
    registry, _, _, retrieval, _ = _registered()
    identifier = _search_call(registry, entity_keys=["franchise:hidden"])
    reversed_range = _search_call(registry, week_from=9, week_to=8)
    assert isinstance(identifier, dict)
    assert isinstance(reversed_range, dict)
    assert identifier["error"]["code"] == "invalid_memory_input"
    assert reversed_range["error"]["code"] == "invalid_memory_input"
    assert retrieval.calls == []


def test_search_maps_editorial_range_and_expansion_preferences() -> None:
    registry, _, _, retrieval, _ = _registered()
    execution = _search_call(
        registry,
        tags=["playoffs"],
        kinds=["storyline"],
        statuses=["active"],
        week_from=4,
        week_to=8,
        limit=3,
        include_evidence=False,
        include_related=False,
    )
    assert isinstance(execution, ToolExecutionResult)
    request = retrieval.calls[0]
    assert request.query.tags == ("playoffs",)
    assert request.query.kinds == (MemoryKind.STORYLINE,)
    assert request.query.statuses == ("active",)
    assert request.query.week_from == 4
    assert request.query.week_to == 8
    assert request.query.limit == 4
    assert request.expand_exact_references is False
    assert request.expand_stable_references is False


def test_semantic_writes_buffer_every_supported_kind_with_provenance() -> None:
    from backend.tests.services.reporter.test_memory_evidence_handoff import setup, saved_source_fact
    registry, context, memory, _, _, _ = setup()
    saved_source_fact(registry, context, week=3)
    with context.bind_tool_execution(UUID(int=101)):
        event = _call(registry, "save_memory_event", **_event_args())
    with context.bind_tool_execution(UUID(int=102)):
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
    with context.bind_tool_execution(UUID(int=103)):
        trigger = _call(
            registry,
            "save_storyline_trigger",
            id="trigger_rematch",
            storyline_id="story_taco",
            trigger_type="rematch",
            event_id="event_week8",
            target_week=12,
            condition={"roster_keys": ["Team Taco", "Waiver Wire"]},
        )
    with context.bind_tool_execution(UUID(int=104)):
        team = _call(registry, "save_team_context", **_note())
    with context.bind_tool_execution(UUID(int=105)):
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
    assert [item.metadata.creating_tool_call_id for item in bundle.proposals] == [
        UUID(int=101),
        UUID(int=102),
        UUID(int=103),
        UUID(int=104),
        UUID(int=105),
    ]
    assert bundle.proposals[0].content.source_hints["week"] == 3
    assert bundle.proposals[0].content.salience == 4
    assert bundle.proposals[0].metadata.week == 3
    assert bundle.proposals[1].content.salience == 2
    assert bundle.proposals[1].metadata.week == 3


def test_stable_id_resolves_internal_replace_revision() -> None:
    from backend.tests.services.reporter.test_memory_evidence_handoff import setup, saved_source_fact
    match = _event_match()
    registry, context, memory, _, _, _ = setup((match,))
    saved_source_fact(registry, context, week=3)
    execution = _execution_call(registry, "save_memory_event", **_event_args())
    assert isinstance(execution, ToolExecutionResult)
    result = execution.result
    assert isinstance(result, dict)
    assert result["saved"] is True
    assert "memory_kind" not in result
    assert "operation" not in result
    assert execution.metadata["memory_activity"] == {
        "items": [{"path": "result", "kind": "event", "operation": "replace"}]
    }
    proposal = memory.take_completed_bundle().proposals[0]
    assert proposal.operation == "replace"
    assert proposal.item_id == match.memory.item.item_id
    assert proposal.expected_item_revision == 7


def test_brief_facts_never_enter_the_canonical_proposal_bundle() -> None:
    _, context, memory, _, adapter = _registered()
    _seed_brief(context)
    assert len(context.brief.brief.facts) == 1
    assert len(context.brief.brief.storylines) == 1
    assert not hasattr(adapter, "buffer_brief_facts")
    assert memory.take_completed_bundle().proposals == ()


def test_repeated_semantic_writes_are_noops_and_conflicts_do_not_duplicate() -> None:
    from backend.tests.services.reporter.test_memory_evidence_handoff import setup, saved_source_fact
    registry, context, memory, _, _, _ = setup()
    saved_source_fact(registry, context, week=3)
    event_args = _event_args()
    card_args = {
        "id": "story_taco",
        "headline": "Taco Takes Control",
        "summary": "The playoff push is real.",
        "status": "active",
        "priority": 4,
        "origin_week": 3,
        "team_keys": ["Team Taco"],
        "evidence_event_ids": ["event_week8"],
    }
    trigger_args = {
        "id": "trigger_rematch",
        "storyline_id": "story_taco",
        "trigger_type": "scheduled_review",
        "target_week": 12,
        "condition": {"review_question": "Does the playoff push hold?"},
    }
    team_args = _note()
    league_args = {
        "key": "playoff_race",
        "value": "The top seed remains unsettled.",
    }
    writes = (
        ("save_memory_event", event_args),
        ("upsert_storyline_memory_card", card_args),
        ("save_storyline_trigger", trigger_args),
        ("save_team_context", team_args),
        ("save_league_note", league_args),
    )

    first_executions = [
        _execution_call(registry, name, **arguments) for name, arguments in writes
    ]
    repeated_executions = [
        _execution_call(registry, name, **arguments) for name, arguments in writes
    ]
    assert all(isinstance(result, ToolExecutionResult) for result in first_executions)
    assert all(
        isinstance(result, ToolExecutionResult) for result in repeated_executions
    )
    first = [result.result for result in first_executions]
    repeated = [result.result for result in repeated_executions]

    assert all(result["saved"] is True for result in first)
    activity = [result.metadata["memory_activity"]["items"][0] for result in first_executions]
    assert {item["kind"] for item in activity} == {
        "event",
        "storyline",
        "trigger",
        "context_note",
    }
    assert all(item["operation"] == "create" for item in activity)
    assert all("memory_kind" not in result for result in first)
    assert all("operation" not in result for result in first)
    assert all(result["saved"] is False and result["no_change"] for result in repeated)
    assert all("memory_activity" not in result.metadata for result in repeated_executions)

    conflicts = (
        ("save_memory_event", {**event_args, "summary": "Conflicting event."}),
        (
            "upsert_storyline_memory_card",
            {**card_args, "summary": "Conflicting storyline."},
        ),
        ("save_storyline_trigger", {**trigger_args, "target_week": 13}),
        ("save_team_context", {**team_args, "narrative": "Conflicting context."}),
        ("save_league_note", {**league_args, "value": "Conflicting note."}),
    )
    rejected = [_call(registry, name, **arguments) for name, arguments in conflicts]
    assert all(result["saved"] is False for result in rejected)
    assert all(
        result["error"]["code"] == "memory_already_selected"
        for result in rejected
    )

    bundle = memory.take_completed_bundle()
    assert len(bundle.proposals) == 5
    assert len({proposal.item_id for proposal in bundle.proposals}) == 5
    assert all(proposal.kind is not MemoryKind.FACT for proposal in bundle.proposals)


def test_storyline_metadata_includes_embedded_trigger_write_outcomes() -> None:
    registry, _, memory, _, _ = _registered()

    execution = _execution_call(
        registry,
        "upsert_storyline_memory_card",
        id="story_taco",
        headline="Taco Takes Control",
        summary="The playoff push is real.",
        status="active",
        team_keys=["Team Taco"],
        trigger_specs=[
            {
                "id": "trigger_rematch",
                "trigger_type": "scheduled_review",
                "target_week": 12,
                "condition": {"review_question": "Does the playoff push hold?"},
            }
        ],
    )

    assert isinstance(execution, ToolExecutionResult)
    result = execution.result
    assert isinstance(result, dict)
    assert result["triggers"] == ["trigger_rematch"]
    assert "trigger_results" not in result
    assert execution.metadata["memory_activity"] == {
        "items": [
            {"path": "result", "kind": "storyline", "operation": "create"},
            {
                "path": "arguments.trigger_specs.0",
                "kind": "trigger",
                "operation": "create",
            },
        ]
    }
    assert [proposal.kind for proposal in memory.take_completed_bundle().proposals] == [
        MemoryKind.STORYLINE,
        MemoryKind.TRIGGER,
    ]


def test_eval_mode_keeps_search_and_skips_legacy_writes() -> None:
    registry, _, memory, retrieval, _ = _registered(allow_memory_writes=False)
    searched = _search_call(registry, text="Taco")
    blocked = _call(registry, "save_memory_event", **_event_args())
    assert isinstance(searched, ToolExecutionResult)
    assert searched.result["memories"] == []
    assert blocked["saved"] is False
    assert blocked["eval_mode"] is True
    assert blocked["recorded"] is False
    assert len(retrieval.calls) == 1
    assert memory.take_completed_bundle().proposals == ()


def test_invalid_legacy_inputs_are_safe_and_do_not_buffer() -> None:
    registry, _, memory, _, _ = _registered()
    missing_source = _event_args()
    missing_source["source_fact_ids"] = []
    verified = _call(registry, "save_memory_event", **missing_source)
    missing_details = _event_args()
    missing_details["source_fact_ids"] = ["not_saved"]
    details = _call(registry, "save_memory_event", **missing_details)
    unresolved = _call(
        registry,
        "save_team_context",
        roster_key="missing",
        narrative="Unknown team.",
    )
    assert verified["error"]["code"] == "invalid_memory_input"
    assert verified["saved"] is False
    assert details["error"]["code"] == "insufficient_event_evidence"
    assert details["saved"] is False
    assert unresolved["error"]["code"] == "roster_not_found"
    assert unresolved["saved"] is False
    assert memory.take_completed_bundle().proposals == ()
