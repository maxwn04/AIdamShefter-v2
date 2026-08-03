"""Integration tests for the reporter v2 entrypoint."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from reporter_memory.context_store import ContextStore
from reporter_v2.config import ReportConfig, TimeRange
from reporter_v2.runner.entrypoint import _persist_brief_facts, generate_article
from reporter_v2.runner.models import ToolCall
from reporter_v2.runner.schemas import Fact, ReportBrief, Storyline


class FakeCompletion:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        if not self.responses:
            return make_response(text="Done.")
        return self.responses.pop(0)


class FakeSleeperLeagueData:
    league_id = "league_123"
    effective_week = 8
    _query_conn = None

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


def make_persistence_completion(*, submit: bool = True) -> FakeCompletion:
    responses = [
        make_response(
            tool_calls=[
                tool_call(
                    "save_fact",
                    {
                        "id": "fact_score",
                        "claim_text": "Team Taco beat Waiver Wire 142.3-98.7.",
                        "data_refs": ["league_snapshot:week=8"],
                        "numbers": {"winner_points": 142.3, "loser_points": 98.7},
                        "category": "score",
                    },
                    "call_fact_score",
                ),
                tool_call(
                    "save_fact",
                    {
                        "id": "fact_record",
                        "claim_text": "Team Taco improved to 7-1.",
                        "data_refs": ["league_snapshot:week=8"],
                        "numbers": {"wins": 7, "losses": 1},
                        "category": "standing",
                    },
                    "call_fact_record",
                ),
            ]
        ),
        make_response(
            tool_calls=[
                tool_call(
                    "save_storyline",
                    {
                        "id": "story_taco",
                        "headline": "Taco Takes Control",
                        "summary": "Team Taco paired a blowout win with a 7-1 record.",
                        "supporting_fact_ids": ["fact_score", "fact_record"],
                        "priority": 1,
                        "tags": ["blowout", "standings"],
                    },
                    "call_story",
                )
            ]
        ),
        make_response(
            tool_calls=[
                tool_call(
                    "write_section",
                    {
                        "name": "lead",
                        "content": "# Taco Takes Control\n\nTeam Taco won big.",
                    },
                    "call_write",
                )
            ]
        ),
    ]
    if submit:
        responses.append(make_response(tool_calls=[tool_call("submit_article")]))
    return FakeCompletion(responses)


def test_generate_article_end_to_end_tool_loop() -> None:
    complete = FakeCompletion(
        [
            make_response(tool_calls=[tool_call("load_procedure", {"name": "research"}, "call_1")]),
            make_response(tool_calls=[tool_call("league_snapshot", {"week": 8}, "call_2")]),
            make_response(
                tool_calls=[
                    tool_call(
                        "save_fact",
                        {
                            "id": "fact_score",
                            "claim_text": "Team Taco beat Waiver Wire 142.3-98.7.",
                            "data_refs": ["league_snapshot:week=8"],
                            "numbers": {"winner_points": 142.3, "loser_points": 98.7},
                            "category": "score",
                        },
                        "call_3",
                    ),
                    tool_call(
                        "save_fact",
                        {
                            "id": "fact_record",
                            "claim_text": "Team Taco improved to 7-1.",
                            "data_refs": ["league_snapshot:week=8"],
                            "numbers": {"wins": 7, "losses": 1},
                            "category": "standing",
                        },
                        "call_4",
                    ),
                    tool_call(
                        "save_fact",
                        {
                            "id": "fact_waiver",
                            "claim_text": "Waiver Wire fell to 2-6.",
                            "data_refs": ["league_snapshot:week=8"],
                            "numbers": {"wins": 2, "losses": 6},
                            "category": "standing",
                        },
                        "call_5",
                    ),
                ]
            ),
            make_response(tool_calls=[tool_call("load_procedure", {"name": "storyline"}, "call_6")]),
            make_response(tool_calls=[tool_call("read_brief", call_id="call_7")]),
            make_response(
                tool_calls=[
                    tool_call(
                        "save_storyline",
                        {
                            "id": "story_taco",
                            "headline": "Taco Takes Control",
                            "summary": "Team Taco paired a blowout win with a 7-1 record.",
                            "supporting_fact_ids": ["fact_score", "fact_record"],
                            "priority": 1,
                            "tags": ["blowout", "standings"],
                        },
                        "call_8",
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
                                    "bullet_points": ["Open on Team Taco's blowout."],
                                    "required_fact_ids": ["fact_score", "fact_record"],
                                    "storyline_ids": ["story_taco"],
                                },
                                {
                                    "title": "Fallout",
                                    "bullet_points": ["Note Waiver Wire's slide."],
                                    "required_fact_ids": ["fact_waiver"],
                                    "storyline_ids": [],
                                },
                            ]
                        },
                        "call_9",
                    ),
                    tool_call(
                        "set_style",
                        {
                            "voice": "sports columnist",
                            "pacing": "fast",
                            "humor_level": 1,
                            "formality": "casual",
                        },
                        "call_10",
                    ),
                ]
            ),
            make_response(tool_calls=[tool_call("load_procedure", {"name": "drafting"}, "call_11")]),
            make_response(tool_calls=[tool_call("read_brief", call_id="call_12")]),
            make_response(
                tool_calls=[
                    tool_call(
                        "write_section",
                        {
                            "name": "lead",
                            "content": "# Taco Takes Control\n\nTeam Taco beat Waiver Wire 142.3-98.7 and moved to 7-1.",
                        },
                        "call_13",
                    ),
                    tool_call(
                        "write_section",
                        {
                            "name": "fallout",
                            "content": "# Fallout\n\nWaiver Wire fell to 2-6 after the loss.",
                        },
                        "call_14",
                    ),
                ]
            ),
            make_response(tool_calls=[tool_call("load_procedure", {"name": "verification"}, "call_15")]),
            make_response(tool_calls=[tool_call("read_article", call_id="call_16")]),
            make_response(tool_calls=[tool_call("read_brief", call_id="call_17")]),
            make_response(tool_calls=[tool_call("submit_article", call_id="call_18")]),
        ]
    )

    output = run(
        generate_article(
            FakeSleeperLeagueData(),
            ReportConfig(
                time_range=TimeRange.single_week(8),
                custom_instructions="weekly recap",
            ),
            model="test-model",
            complete=complete,
        )
    )

    assert "Team Taco beat Waiver Wire 142.3-98.7" in output.article
    assert output.brief.meta.league_id == "league_123"
    assert output.brief.meta.week_start == 8
    assert len(output.brief.facts) == 3
    assert output.brief.storylines[0].headline == "Taco Takes Control"
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
    tool_names = [spec["function"]["name"] for spec in first_request["tools"]]
    assert "save_fact" in tool_names
    assert "save_memory_callback" in tool_names
    assert "write_section" in tool_names
    assert "league_snapshot" in tool_names


def test_generate_article_allows_backtracking_from_drafting_to_research() -> None:
    complete = FakeCompletion(
        [
            make_response(tool_calls=[tool_call("load_procedure", {"name": "drafting"}, "call_1")]),
            make_response(tool_calls=[tool_call("read_brief", call_id="call_2")]),
            make_response(tool_calls=[tool_call("load_procedure", {"name": "research"}, "call_3")]),
            make_response(tool_calls=[tool_call("league_snapshot", {"week": 8}, "call_4")]),
            make_response(
                tool_calls=[
                    tool_call(
                        "save_fact",
                        {
                            "id": "fact_late",
                            "claim_text": "Team Taco was 7-1 after week 8.",
                            "data_refs": ["league_snapshot:week=8"],
                            "numbers": {"wins": 7, "losses": 1},
                            "category": "standing",
                        },
                        "call_5",
                    )
                ]
            ),
            make_response(tool_calls=[tool_call("load_procedure", {"name": "drafting"}, "call_6")]),
            make_response(
                tool_calls=[
                    tool_call(
                        "write_section",
                        {
                            "name": "lead",
                            "content": "# Lead\n\nTeam Taco was 7-1 after week 8.",
                        },
                        "call_7",
                    )
                ]
            ),
            make_response(tool_calls=[tool_call("submit_article", call_id="call_8")]),
        ]
    )

    output = run(
        generate_article(
            FakeSleeperLeagueData(),
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
    assert output.brief.facts[0].id == "fact_late"
    assert "Team Taco was 7-1" in output.article


def test_generate_article_persists_storyline_facts_after_submit(
    tmp_path: Path,
) -> None:
    context_store = ContextStore(
        tmp_path / "context.db",
        league_id="league_123",
        season="2024",
    )
    try:
        output = run(
            generate_article(
                FakeSleeperLeagueData(),
                ReportConfig(time_range=TimeRange.single_week(8)),
                context_store=context_store,
                complete=make_persistence_completion(),
            )
        )

        facts = context_store.get_storyline_facts("story_taco")
        facts_by_id = {fact["fact_id"]: fact for fact in facts}

        assert output.run_log_summary["submitted"] is True
        assert set(facts_by_id) == {"fact_score", "fact_record"}
        assert facts_by_id["fact_score"]["claim_text"] == (
            "Team Taco beat Waiver Wire 142.3-98.7."
        )
        assert facts_by_id["fact_score"]["numbers"] == {
            "winner_points": 142.3,
            "loser_points": 98.7,
        }
    finally:
        context_store.close()


def test_generate_article_post_run_fact_persistence_is_idempotent(
    tmp_path: Path,
) -> None:
    context_store = ContextStore(
        tmp_path / "context.db",
        league_id="league_123",
        season="2024",
    )
    try:
        for _ in range(2):
            run(
                generate_article(
                    FakeSleeperLeagueData(),
                    ReportConfig(time_range=TimeRange.single_week(8)),
                    context_store=context_store,
                    complete=make_persistence_completion(),
                )
            )

        facts = context_store.get_storyline_facts("story_taco")

        assert {fact["fact_id"] for fact in facts} == {"fact_score", "fact_record"}
    finally:
        context_store.close()


def test_persist_brief_facts_skips_missing_supporting_fact_ids(
    tmp_path: Path,
) -> None:
    context_store = ContextStore(
        tmp_path / "context.db",
        league_id="league_123",
        season="2024",
    )
    brief = ReportBrief(
        facts=[
            Fact(
                id="fact_saved",
                claim_text="A supported fact.",
                data_refs=["source"],
            )
        ],
        storylines=[
            Storyline(
                id="story_partial",
                headline="Partial Story",
                summary="One support ID is stale.",
                supporting_fact_ids=["fact_saved", "fact_missing"],
            )
        ],
    )
    try:
        _persist_brief_facts(context_store, brief, week=8)

        facts = context_store.get_storyline_facts("story_partial")

        assert [fact["fact_id"] for fact in facts] == ["fact_saved"]
    finally:
        context_store.close()


def test_generate_article_does_not_persist_facts_without_submit(
    tmp_path: Path,
) -> None:
    context_store = ContextStore(
        tmp_path / "context.db",
        league_id="league_123",
        season="2024",
    )
    try:
        output = run(
            generate_article(
                FakeSleeperLeagueData(),
                ReportConfig(time_range=TimeRange.single_week(8)),
                context_store=context_store,
                complete=make_persistence_completion(submit=False),
            )
        )

        assert output.run_log_summary["submitted"] is False
        assert context_store.get_storyline_facts("story_taco") == []
    finally:
        context_store.close()


def test_generate_article_eval_mode_skips_post_run_fact_persistence(
    tmp_path: Path,
) -> None:
    context_store = ContextStore(
        tmp_path / "context.db",
        league_id="league_123",
        season="2024",
    )
    try:
        output = run(
            generate_article(
                FakeSleeperLeagueData(),
                ReportConfig(time_range=TimeRange.single_week(8)),
                context_store=context_store,
                complete=make_persistence_completion(),
                allow_memory_writes=False,
            )
        )

        assert output.run_log_summary["submitted"] is True
        assert context_store.get_storyline_facts("story_taco") == []
        assert context_store.get_storylines() == []
    finally:
        context_store.close()
