"""Integration tests for the copied platform reporter generator."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from backend.services.datalayer import FrozenRosterIdentity, ResolvedRosterIdentity
from backend.services.memory import (
    GenerationMemoryContext,
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
)
from backend.services.reporter.config import ReportConfig, TimeRange
from backend.services.reporter.definition import prepare_reporter_definition
from backend.services.reporter.generator import generate_article
from backend.services.reporter.runner.completion import CompletionSettings
from backend.services.reporter.runner.models import ToolCall
from backend.services.reporter.runner.recording import ArtifactMutation


class FakeCompletion:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        if not self.responses:
            return make_response(text="Done.")
        return self.responses.pop(0)


class ExecutionRecordingProbe:
    def __init__(self) -> None:
        self.attempt_turns: dict[UUID, int] = {}
        self.successful_turns: dict[int, UUID] = {}
        self.tool_ai_calls: dict[UUID, UUID] = {}
        self.tool_names: list[str] = []
        self.artifact_mutations: list[ArtifactMutation] = []
        self.memory_recalls: list[Any] = []

    def begin_model_attempt(self, attempt):
        attempt_id = uuid4()
        self.attempt_turns[attempt_id] = attempt.turn_number
        return attempt_id

    def finish_model_attempt(self, attempt_id, result):
        if result.status == "succeeded":
            self.successful_turns[self.attempt_turns[attempt_id]] = attempt_id

    def successful_ai_call_id(self, turn_number):
        return self.successful_turns.get(turn_number)

    def begin_tool_execution(self, execution):
        execution_id = uuid4()
        self.tool_names.append(execution.tool_name)
        self.tool_ai_calls[execution_id] = self.successful_turns[
            execution.turn_number
        ]
        return execution_id

    def finish_tool_execution(self, execution_id, result):
        del execution_id, result

    def update_progress(self, progress):
        del progress

    def record_artifact_mutation(self, mutation: ArtifactMutation) -> UUID:
        self.artifact_mutations.append(mutation)
        return uuid4()

    def record_memory_recall(self, recall: Any) -> None:
        self.memory_recalls.append(recall)


class FakeFrozenLeagueData:
    def get_league_snapshot(self, week: int | None = None) -> dict[str, Any]:
        return {
            "week": week,
            "standings": [
                {"team_name": "Team Taco", "wins": 7, "losses": 1, "rank": 1},
                {"team_name": "Waiver Wire", "wins": 2, "losses": 6, "rank": 8},
            ],
            "games": [
                {
                    "winner_team_name": "Team Taco",
                    "loser_team_name": "Waiver Wire",
                    "winner_points": 142.3,
                    "loser_points": 98.7,
                }
            ],
        }

    def run_sql(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        *,
        limit: int = 200,
    ) -> dict[str, Any]:
        del params, limit
        if "FROM leagues" in query:
            return {
                "columns": ["league_id", "name"],
                "rows": [["league_123", "Test League"]],
                "row_count": 1,
            }
        return {"columns": [], "rows": [], "row_count": 0}

    def resolve_roster_identity(self, roster_key: str) -> ResolvedRosterIdentity:
        is_waiver_wire = roster_key == "Waiver Wire"
        return ResolvedRosterIdentity(
            roster_key=roster_key,
            identity=FrozenRosterIdentity(
                competition_id=UUID(int=1),
                competition_season_id=UUID(int=2),
                season_roster_id=UUID(int=5 if is_waiver_wire else 3),
                franchise_id=UUID(int=6 if is_waiver_wire else 4),
                sleeper_roster_id="2" if is_waiver_wire else "1",
                team_name="Waiver Wire" if is_waiver_wire else "Team Taco",
                manager_name="Bob" if is_waiver_wire else "Alice",
            ),
        )


class EmptyMemoryRetrieval:
    def search(
        self,
        *,
        competition_id: UUID,
        revision_id: UUID,
        request: MemoryRetrievalRequest,
    ) -> MemoryRetrievalResult:
        del request
        return MemoryRetrievalResult(
            competition_id=competition_id,
            revision_id=revision_id,
            matches=(),
        )


def make_response(
    *,
    text: str | None = None,
    tool_calls: list[ToolCall] | None = None,
) -> Any:
    raw_calls = [
        SimpleNamespace(
            id=call.id,
            function=SimpleNamespace(
                name=call.name,
                arguments=json.dumps(call.arguments),
            ),
        )
        for call in tool_calls or []
    ]
    message = SimpleNamespace(content=text, tool_calls=raw_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def tool_call(
    name: str,
    arguments: dict[str, Any] | None = None,
    call_id: str | None = None,
) -> ToolCall:
    return ToolCall(
        id=call_id or f"call_{name}",
        name=name,
        arguments=arguments or {},
    )


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_generate_article_end_to_end_tool_loop() -> None:
    recorder = ExecutionRecordingProbe()
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[
                    tool_call("load_procedure", {"name": "research"}, "call_1")
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call("league_snapshot", {"week": 8}, "call_2")
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "save_fact",
                        {
                            "id": "fact_taco_win",
                            "claim_text": (
                                "Team Taco beat Waiver Wire 142.3-98.7 in week 8."
                            ),
                            "data_refs": ["league_snapshot:week=8"],
                            "numbers": {
                                "winner_points": 142.3,
                                "loser_points": 98.7,
                            },
                            "category": "score",
                        },
                        "call_3a",
                    ),
                    tool_call(
                        "save_fact",
                        {
                            "id": "fact_taco_record",
                            "claim_text": "Team Taco improved to 7-1 after week 8.",
                            "data_refs": ["league_snapshot:week=8"],
                            "numbers": {"wins": 7, "losses": 1},
                            "category": "standing",
                        },
                        "call_3b",
                    ),
                    tool_call(
                        "save_fact",
                        {
                            "id": "fact_waiver_record",
                            "claim_text": "Waiver Wire fell to 2-6 after week 8.",
                            "data_refs": ["league_snapshot:week=8"],
                            "numbers": {"wins": 2, "losses": 6},
                            "category": "standing",
                        },
                        "call_3c",
                    ),
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "save_storyline",
                        {
                            "id": "story_taco_control",
                            "headline": "Taco Takes Control",
                            "summary": (
                                "Team Taco paired a blowout win with a 7-1 record."
                            ),
                            "supporting_fact_ids": [
                                "fact_taco_win",
                                "fact_taco_record",
                            ],
                            "priority": 1,
                        },
                        "call_4",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "set_outline",
                        {
                            "sections": [
                                {
                                    "title": "Lead",
                                    "required_fact_ids": [
                                        "fact_taco_win",
                                        "fact_taco_record",
                                    ],
                                    "storyline_ids": ["story_taco_control"],
                                }
                            ]
                        },
                        "call_5",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "create_artifact",
                        {
                            "path": "article.md",
                            "content": (
                                "# Taco Takes Control\n\n"
                                "Team Taco beat Waiver Wire 142.3-98.7 and "
                                "moved to 7-1.\n\n"
                                "## Fallout\n\nWaiver Wire fell to 2-6 after the loss."
                            ),
                        },
                        "call_9",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "load_procedure", {"name": "verification"}, "call_10"
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "edit_artifact",
                        {
                            "path": "article.md",
                            "old_text": "moved to 7-1",
                            "new_text": "improved to 7-1",
                            "expected_revision": 1,
                        },
                        "call_12",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "submit_artifact",
                        {"path": "article.md", "expected_revision": 2},
                        "call_13",
                    )
                ]
            ),
        ]
    )

    output = run(
        generate_article(
            FakeFrozenLeagueData(),
            ReportConfig(
                time_range=TimeRange.single_week(8),
                custom_instructions="weekly recap",
            ),
            completion=CompletionSettings(model="test-model"),
            complete=complete,
            recorder=recorder,
        )
    )

    artifacts = {artifact.path: artifact for artifact in output.artifacts}

    assert output.submitted_path == "article.md"
    assert tuple(artifact.path for artifact in output.artifacts) == (
        "article.md",
        "research_brief.md",
    )
    assert artifacts["article.md"].revision == 2
    assert "improved to 7-1" in artifacts["article.md"].content
    assert "moved to 7-1" not in artifacts["article.md"].content
    assert len(artifacts["article.md"].content_hash) == 64
    assert artifacts["research_brief.md"].revision == 3
    assert "League ID: league_123" in artifacts["research_brief.md"].content
    assert "Team Taco beat Waiver Wire 142.3-98.7" in artifacts[
        "research_brief.md"
    ].content
    assert "Taco Takes Control" in artifacts["research_brief.md"].content
    assert output.run_log_summary["submitted"] is True
    assert output.run_log_summary["total_turns"] == 9
    assert output.run_log_summary["procedures_loaded"] == [
        "research",
        "verification",
    ]
    assert output.run_log_summary["brief"] == {
        "revision": 5,
        "projection_revision": 5,
        "fact_count": 3,
        "callback_count": 0,
        "storyline_count": 1,
        "outline_section_count": 1,
        "stale_callback_ids": [],
        "stale_storyline_ids": [],
        "outline_stale": False,
        "readiness_warnings": [],
        "first_fact_turn": 3,
        "first_storyline_turn": 4,
        "first_draft_turn": 6,
        "submission_turn": 9,
    }
    assert any(
        entry["event_type"] == "tool_call"
        and entry["data"]["tool_name"] == "league_snapshot"
        and entry["data"]["params"] == {"week": 8}
        for entry in output.run_log_entries
    )
    first_request = complete.requests[0]
    assert first_request["model"] == "test-model"
    tool_names = {spec["function"]["name"] for spec in first_request["tools"]}
    assert {
        "list_artifacts",
        "read_artifact",
        "create_artifact",
        "edit_artifact",
        "submit_artifact",
    }.issubset(tool_names)
    assert {"save_fact", "read_brief", "save_storyline", "set_outline"}.issubset(
        tool_names
    )
    assert {"write_section", "submit_article"}.isdisjoint(tool_names)
    assert "league_snapshot" in tool_names
    histories = {
        path: [
            mutation
            for mutation in recorder.artifact_mutations
            if mutation.path == path
        ]
        for path in ("research_brief.md", "article.md")
    }
    assert [item.revision for item in histories["research_brief.md"]] == [1, 2, 3]
    assert [item.revision for item in histories["article.md"]] == [1, 2]
    turn_three_tool_ids = [
        execution_id
        for execution_id, ai_call_id in recorder.tool_ai_calls.items()
        if ai_call_id == recorder.successful_turns[3]
    ]
    assert histories["research_brief.md"][0].source_tool_call_id == (
        turn_three_tool_ids[-1]
    )
    tool_mutations = histories["research_brief.md"] + histories["article.md"]
    assert all(item.source_tool_call_id is not None for item in tool_mutations)


def test_generate_article_keeps_final_brief_facts_out_of_canonical_memory() -> None:
    recorder = ExecutionRecordingProbe()
    memory_context = GenerationMemoryContext(
        competition_id=UUID(int=1),
        generation_id=uuid4(),
        pinned_revision_id=uuid4(),
        retrieval=EmptyMemoryRetrieval(),
        competition_season_id=UUID(int=2),
        week=8,
    )
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[
                    tool_call(
                        "save_fact",
                        {
                            "id": "fact_taco_win",
                            "claim_text": "Team Taco won in Week 8.",
                            "data_refs": ["league_snapshot:week=8"],
                            "numbers": {"week": 8},
                            "category": "score",
                        },
                        "fact-call",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "save_storyline",
                        {
                            "id": "story_taco_push",
                            "headline": "Taco's push is getting louder.",
                            "summary": (
                                "A Week 8 win strengthened the contender arc."
                            ),
                            "supporting_fact_ids": ["fact_taco_win"],
                            "priority": 4,
                            "tags": ["playoffs"],
                        },
                        "storyline-call",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "create_artifact",
                        {"path": "article.md", "content": "# Week 8\n\nTaco won."},
                        "create-call",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "submit_artifact",
                        {"path": "article.md", "expected_revision": 1},
                        "submit-call",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "complete_memory_review",
                        {},
                        "no-op-closeout-call",
                    )
                ]
            ),
        ]
    )

    output = run(
        generate_article(
            FakeFrozenLeagueData(),  # type: ignore[arg-type]
            ReportConfig.for_week(8),
            memory_context=memory_context,
            completion=CompletionSettings(model="test-model"),
            complete=complete,
            recorder=recorder,
        )
    )

    assert output.submitted_path == "article.md"
    prepared = prepare_reporter_definition(memory_enabled=True)
    submit_result = next(
        json.loads(message["content"])
        for message in complete.requests[-1]["messages"]
        if message.get("tool_call_id") == "submit-call"
    )
    assert submit_result["next_action"] == {
        "type": "mandatory_procedure",
        "name": "memory_closeout",
        "content": prepared.procedure_contents["memory_closeout"],
        "completion_tool": "complete_memory_review",
        "memory_writes_enabled": True,
    }
    assert all(
        request["tools"] == complete.requests[0]["tools"]
        for request in complete.requests
    )
    assert output.run_log_summary["memory_closeout"]["status"] == "completed"
    assert output.run_log_summary["memory_closeout"]["no_op"] is True
    assert memory_context.take_completed_bundle().proposals == ()


@pytest.mark.parametrize(
    ("allow_memory_writes", "expected_proposals"),
    [(True, 5), (False, 0)],
)
def test_generation_closeout_buffers_all_live_kinds_and_backtest_noop(
    allow_memory_writes: bool,
    expected_proposals: int,
) -> None:
    recorder = ExecutionRecordingProbe()
    memory_context = GenerationMemoryContext(
        competition_id=UUID(int=1),
        generation_id=uuid4(),
        pinned_revision_id=uuid4(),
        retrieval=EmptyMemoryRetrieval(),
        competition_season_id=UUID(int=2),
        week=8,
    )
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[
                    tool_call(
                        "save_fact",
                        {
                            "id": "fact_closeout_fixture",
                            "claim_text": "Week 8 supplied a verified fact.",
                            "data_refs": ["league_snapshot:week=8"],
                        },
                        "fact-call",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "create_artifact",
                        {"path": "article.md", "content": "# Week 8\n\nVerified."},
                        "create-call",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "submit_artifact",
                        {"path": "article.md", "expected_revision": 1},
                        "submit-call",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "save_memory_event",
                        {
                            "id": "event_closeout_matchup",
                            "event_type": "matchup",
                            "week": 8,
                            "headline": "Team Taco won the Week 8 matchup.",
                            "summary": "Team Taco defeated Waiver Wire.",
                            "importance": 4,
                            "confidence": "verified",
                            "source_refs": ["league_snapshot:week=8"],
                            "matchup_id": "week-8-1",
                            "details": {
                                "kind": "matchup",
                                "winner_roster_key": "Team Taco",
                                "loser_roster_key": "Waiver Wire",
                                "sleeper_matchup_id": "week-8-1",
                            },
                        },
                        "event-memory-call",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "upsert_storyline_memory_card",
                        {
                            "id": "story_closeout_push",
                            "headline": "Taco Takes Control",
                            "summary": "The playoff push is real.",
                            "status": "active",
                            "priority": 4,
                            "origin_week": 8,
                            "team_keys": ["Team Taco"],
                            "evidence_event_ids": ["event_closeout_matchup"],
                        },
                        "storyline-memory-call",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "complete_memory_review",
                        {},
                        "complete-call",
                    ),
                    tool_call(
                        "save_league_note",
                        {
                            "key": "closeout_note",
                            "value": "A durable league-wide closeout note.",
                        },
                        "memory-call",
                    ),
                    tool_call(
                        "save_team_context",
                        {
                            "roster_key": "Team Taco",
                            "narrative": "Team Taco is surging toward the playoffs.",
                            "outlook": "surging",
                        },
                        "team-memory-call",
                    ),
                    tool_call(
                        "save_storyline_trigger",
                        {
                            "id": "trigger_closeout_rematch",
                            "storyline_id": "story_closeout_push",
                            "trigger_type": "rematch",
                            "target_week": 12,
                            "condition": {
                                "roster_keys": ["Team Taco", "Waiver Wire"]
                            },
                        },
                        "trigger-memory-call",
                    ),
                    tool_call(
                        "edit_artifact",
                        {
                            "path": "article.md",
                            "old_text": "Verified.",
                            "new_text": "Changed after submission.",
                            "expected_revision": 1,
                        },
                        "immutable-call",
                    ),
                ]
            ),
        ]
    )

    output = run(
        generate_article(
            FakeFrozenLeagueData(),  # type: ignore[arg-type]
            ReportConfig.for_week(8),
            memory_context=memory_context,
            completion=CompletionSettings(model="test-model"),
            complete=complete,
            allow_memory_writes=allow_memory_writes,
            recorder=recorder,
        )
    )

    summary = output.run_log_summary["memory_closeout"]
    bundle = memory_context.take_completed_bundle()
    assert summary["status"] == "completed"
    assert summary["proposal_counts"]["total"] == expected_proposals
    assert summary["no_op"] is (expected_proposals == 0)
    assert len(bundle.proposals) == expected_proposals
    events = [
        entry["data"]["event"]
        for entry in output.run_log_entries
        if entry["event_type"] == "memory_closeout"
    ]
    assert events[:3] == [
        "article_submitted",
        "closeout_activated",
        "memory_review_completed",
    ]
    assert ("memory_review_noop" in events) is (expected_proposals == 0)
    assert output.submitted_artifact is not None
    assert output.submitted_artifact.content == "# Week 8\n\nVerified."
    assert output.submitted_artifact.revision == 1
    if allow_memory_writes:
        assert summary["proposal_counts"]["by_kind"] == {
            "context_note": 2,
            "event": 1,
            "storyline": 1,
            "trigger": 1,
        }
        assert summary["proposal_counts"]["by_operation"] == {"create": 5}
        kinds = [proposal.kind.value for proposal in bundle.proposals]
        assert kinds.count("event") == 1
        assert kinds.count("storyline") == 1
        assert kinds.count("trigger") == 1
        assert kinds.count("context_note") == 2
        assert all(proposal.operation == "create" for proposal in bundle.proposals)
        assert all(
            proposal.metadata.creating_tool_call_id is not None
            for proposal in bundle.proposals
        )
        assert all(proposal.kind.value != "fact" for proposal in bundle.proposals)
    else:
        assert summary["proposal_counts"]["by_kind"] == {}
        assert summary["proposal_counts"]["by_operation"] == {}


def test_generation_starts_with_exact_recorded_automatic_recall_context() -> None:
    from backend.tests.services.reporter.test_memory_recall import (
        COMPETITION_ID,
        CUTOFF,
        REVISION_ID,
        Retrieval,
        SEASON_ID,
        _note,
        _trigger,
    )

    recorder = ExecutionRecordingProbe()
    retrieval = Retrieval(
        triggers=(_trigger(80, target_week=8, target_at=CUTOFF),),
        notes=(_note(81, {"scope": "competition", "note_key": "league"}),),
    )
    memory_context = GenerationMemoryContext(
        competition_id=COMPETITION_ID,
        generation_id=uuid4(),
        pinned_revision_id=REVISION_ID,
        retrieval=retrieval,
        competition_season_id=SEASON_ID,
        week=8,
        knowledge_cutoff_at=CUTOFF,
    )
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[
                    tool_call(
                        "create_artifact",
                        {"path": "article.md", "content": "# Week 8\n\nTaco won."},
                        "create-call",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "submit_artifact",
                        {"path": "article.md", "expected_revision": 1},
                        "submit-call",
                    )
                ]
            ),
        ]
    )

    output = run(
        generate_article(
            FakeFrozenLeagueData(),  # type: ignore[arg-type]
            ReportConfig.for_week(8),
            memory_context=memory_context,
            completion=CompletionSettings(model="test-model"),
            complete=complete,
            recorder=recorder,
        )
    )

    assert output.artifacts[0].path == "article.md"
    assert len(recorder.memory_recalls) == 1
    recorded = recorder.memory_recalls[0]
    messages = complete.requests[0]["messages"]
    assert [message["role"] for message in messages[:3]] == [
        "system",
        "user",
        "user",
    ]
    assert messages[1]["content"] == recorded.result_text
    assert all(
        request["messages"][1]["content"] == recorded.result_text
        for request in complete.requests
    )
    assert "due_callbacks" in messages[1]["content"]
    assert "standing_context" in messages[1]["content"]
    assert "Context note 81" in messages[1]["content"]
    assert "pinned_revision_id" not in messages[1]["content"]
    assert recorded.metadata["pinned_revision_id"] == str(REVISION_ID)
    assert "search_memory" not in recorder.tool_names


def test_generation_can_disable_automatic_recall_without_removing_memory_tools() -> None:
    from backend.tests.services.reporter.test_memory_recall import (
        COMPETITION_ID,
        CUTOFF,
        REVISION_ID,
        Retrieval,
        SEASON_ID,
        _note,
        _trigger,
    )

    recorder = ExecutionRecordingProbe()
    memory_context = GenerationMemoryContext(
        competition_id=COMPETITION_ID,
        generation_id=uuid4(),
        pinned_revision_id=REVISION_ID,
        retrieval=Retrieval(
            triggers=(_trigger(80, target_week=8, target_at=CUTOFF),),
            notes=(_note(81, {"scope": "competition", "note_key": "league"}),),
        ),
        competition_season_id=SEASON_ID,
        week=8,
        knowledge_cutoff_at=CUTOFF,
    )
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[
                    tool_call(
                        "create_artifact",
                        {"path": "article.md", "content": "# Week 8\n\nTaco won."},
                        "create-call",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "submit_artifact",
                        {"path": "article.md", "expected_revision": 1},
                        "submit-call",
                    )
                ]
            ),
        ]
    )

    run(
        generate_article(
            FakeFrozenLeagueData(),  # type: ignore[arg-type]
            ReportConfig.for_week(8),
            memory_context=memory_context,
            completion=CompletionSettings(model="test-model"),
            complete=complete,
            recorder=recorder,
            automatic_memory_recall=False,
        )
    )

    assert recorder.memory_recalls == []
    assert [message["role"] for message in complete.requests[0]["messages"][:2]] == [
        "system",
        "user",
    ]
    assert complete.requests[0]["messages"][1]["content"].startswith(
        "Generate a fantasy football article"
    )
    tool_names = [
        definition["function"]["name"]
        for definition in complete.requests[0]["tools"]
    ]
    assert "search_memory" in tool_names
    assert "complete_memory_review" in tool_names


def test_generate_article_allows_backtracking_from_drafting_to_research() -> None:
    complete = FakeCompletion(
        [
            make_response(
                tool_calls=[
                    tool_call("load_procedure", {"name": "drafting"}, "call_1")
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "read_brief",
                        {},
                        "call_2",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call("load_procedure", {"name": "research"}, "call_3")
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call("league_snapshot", {"week": 8}, "call_4")
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "save_fact",
                        {
                            "id": "fact_taco_record",
                            "claim_text": "Team Taco was 7-1 after week 8.",
                            "data_refs": ["league_snapshot:week=8"],
                            "numbers": {"wins": 7, "losses": 1},
                            "category": "standing",
                        },
                        "call_5",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call("load_procedure", {"name": "drafting"}, "call_6")
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "create_artifact",
                        {
                            "path": "article.md",
                            "content": "# Lead\n\nTeam Taco was 7-1 after week 8.",
                        },
                        "call_7",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "submit_artifact",
                        {"path": "article.md", "expected_revision": 1},
                        "call_8",
                    )
                ]
            ),
        ]
    )

    output = run(
        generate_article(
            FakeFrozenLeagueData(),
            ReportConfig(time_range=TimeRange.single_week(8)),
            complete=complete,
        )
    )

    assert output.run_log_summary["submitted"] is True
    assert output.run_log_summary["procedures_loaded"] == [
        "drafting",
        "research",
        "drafting",
    ]
    artifacts = {artifact.path: artifact for artifact in output.artifacts}
    assert output.submitted_path == "article.md"
    assert artifacts["research_brief.md"].revision == 1
    assert "Team Taco was 7-1" in artifacts["research_brief.md"].content
    assert artifacts["article.md"].revision == 1
    assert "Team Taco was 7-1" in artifacts["article.md"].content
