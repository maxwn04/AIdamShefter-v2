"""Integration tests for the copied platform reporter generator."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from backend.services.datalayer import FrozenRosterIdentity, ResolvedRosterIdentity
from backend.services.memory import (
    GenerationMemoryContext,
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
)
from backend.services.reporter.config import ReportConfig, TimeRange
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
        self.artifact_mutations: list[ArtifactMutation] = []

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
        return ResolvedRosterIdentity(
            roster_key=roster_key,
            identity=FrozenRosterIdentity(
                competition_id=UUID(int=1),
                competition_season_id=UUID(int=2),
                season_roster_id=UUID(int=3),
                franchise_id=UUID(int=4),
                sleeper_roster_id="1",
                team_name="Team Taco",
                manager_name="Alice",
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
    assert artifacts["research_brief.md"].revision == 5
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
    assert [item.revision for item in histories["research_brief.md"]] == [1, 2, 3, 4, 5]
    assert [item.revision for item in histories["article.md"]] == [1, 2]
    tool_mutations = histories["research_brief.md"] + histories["article.md"]
    assert all(item.source_tool_call_id is not None for item in tool_mutations)


def test_generate_article_buffers_typed_memory_with_tool_provenance() -> None:
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
                        "propose_fact",
                        {
                            "content": {
                                "claim": "Team Taco won in Week 8.",
                                "category": "matchup_result",
                                "numbers": {"week": 8},
                                "confidence": "inferred",
                                "subjects": [
                                    {
                                        "kind": "franchise",
                                        "roster_key": "Team Taco",
                                        "role": "subject",
                                    }
                                ],
                            }
                        },
                        "memory-call",
                    )
                ]
            ),
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
                        "brief-call",
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
    bundle = memory_context.take_completed_bundle()
    assert len(bundle.proposals) == 1
    proposal = bundle.proposals[0]
    assert proposal.content.subjects[0].id == UUID(int=4)
    assert proposal.metadata.creating_tool_call_id in recorder.tool_ai_calls


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
