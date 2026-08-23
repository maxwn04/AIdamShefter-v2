"""Integration tests for the copied platform reporter generator."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

from backend.services.reporter.config import ReportConfig, TimeRange
from backend.services.reporter.generator import generate_article
from backend.services.reporter.runner.completion import CompletionSettings
from backend.services.reporter.runner.models import ToolCall


class FakeCompletion:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        if not self.responses:
            return make_response(text="Done.")
        return self.responses.pop(0)


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
                        "read_artifact",
                        {"path": "research/brief.md"},
                        "call_3",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "edit_artifact",
                        {
                            "path": "research/brief.md",
                            "old_text": "<!-- INSERT VERIFIED FACTS ABOVE THIS LINE -->",
                            "new_text": (
                                "- Team Taco beat Waiver Wire 142.3-98.7.\n"
                                "- Team Taco improved to 7-1.\n"
                                "- Waiver Wire fell to 2-6.\n\n"
                                "<!-- INSERT VERIFIED FACTS ABOVE THIS LINE -->"
                            ),
                            "expected_revision": 1,
                        },
                        "call_4",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call("load_procedure", {"name": "storyline"}, "call_5")
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "edit_artifact",
                        {
                            "path": "research/brief.md",
                            "old_text": "<!-- INSERT STORYLINES ABOVE THIS LINE -->",
                            "new_text": (
                                "- Taco Takes Control: Team Taco paired a blowout "
                                "win with a 7-1 record.\n\n"
                                "<!-- INSERT STORYLINES ABOVE THIS LINE -->"
                            ),
                            "expected_revision": 2,
                        },
                        "call_6",
                    )
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call("load_procedure", {"name": "drafting"}, "call_7")
                ]
            ),
            make_response(
                tool_calls=[
                    tool_call(
                        "read_artifact",
                        {"path": "research/brief.md"},
                        "call_8",
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
                        "read_artifact", {"path": "article.md"}, "call_11"
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
        )
    )

    artifacts = {artifact.path: artifact for artifact in output.artifacts}

    assert output.submitted_path == "article.md"
    assert tuple(artifact.path for artifact in output.artifacts) == (
        "article.md",
        "research/brief.md",
    )
    assert artifacts["article.md"].revision == 2
    assert "improved to 7-1" in artifacts["article.md"].content
    assert "moved to 7-1" not in artifacts["article.md"].content
    assert len(artifacts["article.md"].content_hash) == 64
    assert artifacts["research/brief.md"].revision == 3
    assert "League ID: league_123" in artifacts["research/brief.md"].content
    assert "Team Taco beat Waiver Wire 142.3-98.7" in artifacts[
        "research/brief.md"
    ].content
    assert "Taco Takes Control" in artifacts["research/brief.md"].content
    assert output.run_log_summary["submitted"] is True
    assert output.run_log_summary["procedures_loaded"] == [
        "research",
        "storyline",
        "drafting",
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
    assert {"save_fact", "read_brief", "write_section", "submit_article"}.isdisjoint(
        tool_names
    )
    assert "league_snapshot" in tool_names


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
                        "read_artifact",
                        {"path": "research/brief.md"},
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
                        "edit_artifact",
                        {
                            "path": "research/brief.md",
                            "old_text": "<!-- INSERT VERIFIED FACTS ABOVE THIS LINE -->",
                            "new_text": (
                                "- Team Taco was 7-1 after week 8.\n\n"
                                "<!-- INSERT VERIFIED FACTS ABOVE THIS LINE -->"
                            ),
                            "expected_revision": 1,
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
    assert artifacts["research/brief.md"].revision == 2
    assert "Team Taco was 7-1" in artifacts["research/brief.md"].content
    assert artifacts["article.md"].revision == 1
    assert "Team Taco was 7-1" in artifacts["article.md"].content
