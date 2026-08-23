"""Tests for the typed generation-memory reporter adapter."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from backend.services.datalayer import (
    AmbiguousRosterIdentity,
    FrozenRosterIdentity,
    ResolvedRosterIdentity,
    RosterIdentityNotFound,
)
from backend.services.memory import (
    GenerationMemoryContext,
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
    register_memory_tools,
)
from backend.services.reporter.runner.tools.registry import ToolRegistry


COMPETITION_ID = UUID(int=1)
SEASON_ID = UUID(int=2)
TACO_ROSTER_ID = UUID(int=3)
TACO_FRANCHISE_ID = UUID(int=4)
WIRE_ROSTER_ID = UUID(int=5)
WIRE_FRANCHISE_ID = UUID(int=6)


class RecordingRetrieval:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, UUID, MemoryRetrievalRequest]] = []

    def search(
        self,
        *,
        competition_id: UUID,
        revision_id: UUID,
        request: MemoryRetrievalRequest,
    ) -> MemoryRetrievalResult:
        self.calls.append((competition_id, revision_id, request))
        return MemoryRetrievalResult(
            competition_id=competition_id,
            revision_id=revision_id,
            matches=(),
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
        if roster_key == "ambiguous":
            return AmbiguousRosterIdentity(
                roster_key=roster_key,
                matches=tuple(self.identities.values()),
            )
        identity = self.identities.get(roster_key)
        if identity is None:
            return RosterIdentityNotFound(roster_key=roster_key)
        return ResolvedRosterIdentity(roster_key=roster_key, identity=identity)


def _registered(
    *,
    allow_memory_writes: bool = True,
) -> tuple[ToolRegistry, ToolContext, GenerationMemoryContext, RecordingRetrieval]:
    retrieval = RecordingRetrieval()
    memory_context = GenerationMemoryContext(
        competition_id=COMPETITION_ID,
        generation_id=uuid4(),
        pinned_revision_id=uuid4(),
        retrieval=retrieval,
        competition_season_id=SEASON_ID,
        week=8,
    )
    registry = ToolRegistry()
    register_memory_tools(
        registry,
        memory_context,
        FrozenData(),  # type: ignore[arg-type]
        allow_memory_writes=allow_memory_writes,
    )
    tool_context = ToolContext(
        artifacts=ArtifactStore(),
        procedures=ProcedureState(),
        log=RunLog(session_id="memory-tools"),
    )
    registry.set_context(tool_context)
    return registry, tool_context, memory_context, retrieval


def _call(registry: ToolRegistry, name: str, **arguments: Any) -> dict[str, Any]:
    handler = registry.get_handler(name)
    assert handler is not None
    result = handler(**arguments)
    assert isinstance(result, dict)
    return result


def _fact_content(*, roster_key: str = "Team Taco") -> dict[str, Any]:
    return {
        "claim": "Team Taco won in Week 8.",
        "category": "matchup_result",
        "numbers": {"week": 8},
        "confidence": "inferred",
        "subjects": [
            {"kind": "franchise", "roster_key": roster_key, "role": "subject"},
            {
                "kind": "season_roster",
                "roster_key": roster_key,
                "role": "subject",
            },
        ],
        "source_hints": {"tool": "team_game", "week": 8},
    }


def _event_content() -> dict[str, Any]:
    return {
        "event_type": "matchup",
        "headline": "Taco won the Week 8 matchup.",
        "summary": "Team Taco defeated Waiver Wire.",
        "salience": 4,
        "confidence": "inferred",
        "details": {
            "kind": "matchup",
            "winner_roster_key": "Team Taco",
            "loser_roster_key": "Waiver Wire",
            "sleeper_matchup_id": "week-8-1",
        },
    }


def _storyline_content(event_version_id: UUID | None = None) -> dict[str, Any]:
    evidence = []
    if event_version_id is not None:
        evidence.append(
            {"kind": "event", "version_id": event_version_id, "role": "origin"}
        )
    return {
        "headline": "Taco's push is getting louder.",
        "summary": "A Week 8 win strengthened the season-long contender arc.",
        "status": "active",
        "arc_type": "playoff_push",
        "salience": 4,
        "tags": ["playoffs"],
        "subjects": [
            {"kind": "franchise", "roster_key": "Team Taco", "role": "focus"}
        ],
        "evidence": evidence,
    }


def _trigger_content(*, storyline_item_id: UUID | None = None) -> dict[str, Any]:
    return {
        "trigger_type": "rematch",
        "fire_policy": "one_shot",
        "target_storyline_item_id": storyline_item_id,
        "target_week": 12,
        "condition": {
            "kind": "rematch",
            "roster_keys": ["Team Taco", "Waiver Wire"],
        },
    }


def _note_content() -> dict[str, Any]:
    return {
        "narrative": "Team Taco is surging toward the playoffs.",
        "outlook": "Contending with a favorable remaining schedule.",
        "tags": ["playoffs", "surging"],
    }


def test_registers_only_the_typed_memory_vocabulary() -> None:
    registry, _, _, _ = _registered()

    assert registry.tool_names == [
        "search_memory",
        "propose_fact",
        "replace_fact",
        "propose_event",
        "replace_event",
        "propose_storyline",
        "replace_storyline",
        "propose_trigger",
        "replace_trigger",
        "propose_context_note",
        "replace_context_note",
    ]
    assert registry.tool_specs == MEMORY_TOOL_SPECS
    assert registry.tool_implementation_versions == [
        (name, MEMORY_TOOL_IMPLEMENTATION_VERSION) for name in registry.tool_names
    ]


def test_search_is_pinned_and_resolves_both_team_identity_keys() -> None:
    registry, _, memory_context, retrieval = _registered()

    result = _call(
        registry,
        "search_memory",
        text="playoff push",
        team_keys=["Team Taco"],
        kinds=["storyline", "context_note"],
        tags=["Playoffs"],
        expand_exact_references=True,
    )

    assert result == {
        "ok": True,
        "competition_id": str(COMPETITION_ID),
        "revision_id": str(memory_context.pinned_revision_id),
        "matches": [],
    }
    competition_id, revision_id, request = retrieval.calls[0]
    assert competition_id == COMPETITION_ID
    assert revision_id == memory_context.pinned_revision_id
    assert request.query.entity_keys == (
        f"franchise:{TACO_FRANCHISE_ID}",
        f"season_roster:{TACO_ROSTER_ID}",
    )
    assert request.query.kinds == (MemoryKind.STORYLINE, MemoryKind.CONTEXT_NOTE)
    assert request.query.tags == ("playoffs",)
    assert request.expand_exact_references is True


def test_all_propose_and_replace_tools_buffer_complete_typed_content() -> None:
    registry, tool_context, memory_context, _ = _registered()
    source_tool_call_id = uuid4()

    with tool_context.bind_tool_execution(source_tool_call_id):
        event = _call(registry, "propose_event", content=_event_content())
        event_version_id = UUID(event["proposal"]["version_id"])
        fact = _call(registry, "propose_fact", content=_fact_content())
        storyline = _call(
            registry,
            "propose_storyline",
            content=_storyline_content(event_version_id),
        )
        storyline_item_id = UUID(storyline["proposal"]["item_id"])
        trigger = _call(
            registry,
            "propose_trigger",
            content=_trigger_content(storyline_item_id=storyline_item_id),
        )
        note = _call(
            registry,
            "propose_context_note",
            identity={
                "scope": "franchise",
                "roster_key": "Team Taco",
                "note_key": "weekly_outlook",
            },
            content=_note_content(),
        )

        replacements = [
            _call(
                registry,
                "replace_fact",
                item_id=str(uuid4()),
                expected_item_revision=1,
                content=_fact_content(),
            ),
            _call(
                registry,
                "replace_event",
                item_id=str(uuid4()),
                expected_item_revision=2,
                content=_event_content(),
            ),
            _call(
                registry,
                "replace_storyline",
                item_id=str(uuid4()),
                expected_item_revision=3,
                content=_storyline_content(),
            ),
            _call(
                registry,
                "replace_trigger",
                item_id=str(uuid4()),
                expected_item_revision=4,
                content=_trigger_content(),
            ),
            _call(
                registry,
                "replace_context_note",
                item_id=str(uuid4()),
                expected_item_revision=5,
                content=_note_content(),
            ),
        ]

    assert all(result["ok"] for result in (event, fact, storyline, trigger, note))
    assert all(result["ok"] for result in replacements)
    bundle = memory_context.take_completed_bundle()
    assert [proposal.operation for proposal in bundle.proposals] == [
        *("create" for _ in range(5)),
        *("replace" for _ in range(5)),
    ]
    assert [proposal.kind for proposal in bundle.proposals] == [
        MemoryKind.EVENT,
        MemoryKind.FACT,
        MemoryKind.STORYLINE,
        MemoryKind.TRIGGER,
        MemoryKind.CONTEXT_NOTE,
        MemoryKind.FACT,
        MemoryKind.EVENT,
        MemoryKind.STORYLINE,
        MemoryKind.TRIGGER,
        MemoryKind.CONTEXT_NOTE,
    ]
    assert all(
        proposal.metadata.creating_tool_call_id == source_tool_call_id
        for proposal in bundle.proposals
    )
    assert bundle.proposals[0].content.details.winner_franchise_id == (
        TACO_FRANCHISE_ID
    )
    assert [subject.id for subject in bundle.proposals[1].content.subjects] == [
        TACO_FRANCHISE_ID,
        TACO_ROSTER_ID,
    ]
    assert bundle.proposals[4].context_note_identity.franchise_id == (
        TACO_FRANCHISE_ID
    )


def test_invalid_inputs_are_safe_and_do_not_change_the_buffer() -> None:
    registry, _, memory_context, _ = _registered()

    source_backed = _fact_content()
    source_backed["confidence"] = "source_backed"
    invalid = _call(registry, "propose_fact", content=source_backed)
    missing = _call(
        registry,
        "propose_fact",
        content=_fact_content(roster_key="missing"),
    )
    ambiguous = _call(
        registry,
        "propose_fact",
        content=_fact_content(roster_key="ambiguous"),
    )
    created = _call(registry, "propose_fact", content=_fact_content())
    local_replace = _call(
        registry,
        "replace_fact",
        item_id=created["proposal"]["item_id"],
        expected_item_revision=1,
        content=_fact_content(),
    )

    assert invalid["error"]["code"] == "invalid_memory_input"
    assert missing["error"]["code"] == "roster_not_found"
    assert ambiguous["error"]["code"] == "roster_ambiguous"
    assert local_replace["error"]["code"] == "proposal_local_replacement"
    bundle = memory_context.take_completed_bundle()
    assert len(bundle.proposals) == 1


def test_eval_mode_keeps_search_and_skips_all_proposals() -> None:
    registry, _, memory_context, retrieval = _registered(allow_memory_writes=False)

    search = _call(registry, "search_memory", text="Taco")
    for tool_name in registry.tool_names[1:]:
        result = _call(registry, tool_name)
        assert result["ok"] is True
        assert result["proposed"] is False
        assert result["eval_mode"] is True

    assert search["ok"] is True
    assert len(retrieval.calls) == 1
    assert memory_context.take_completed_bundle().proposals == ()


def test_buffered_proposals_never_appear_in_same_run_searches() -> None:
    registry, _, memory_context, retrieval = _registered()

    proposed = _call(registry, "propose_storyline", content=_storyline_content())
    searched = _call(registry, "search_memory", text="Taco's push")

    assert proposed["ok"] is True
    assert searched["matches"] == []
    assert len(retrieval.calls) == 1
    assert len(memory_context.take_completed_bundle().proposals) == 1
