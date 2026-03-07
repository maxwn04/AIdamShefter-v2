"""Tests for the storyline curator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reporter.agent.config import ReportConfig, TimeRange
from reporter.agent.curator import StorylineCurator
from reporter.agent.schemas import CuratedContext, StorylineCandidate


class TestCuratedContextSchema:
    def test_empty_construction(self):
        ctx = CuratedContext(reasoning="none")
        assert ctx.relevant_storyline_ids == []
        assert ctx.new_storyline_candidates == []
        assert ctx.reasoning == "none"

    def test_with_ids_and_candidates(self):
        ctx = CuratedContext(
            relevant_storyline_ids=["story_1", "story_2"],
            new_storyline_candidates=[
                StorylineCandidate(
                    suggested_headline="New Rivalry",
                    reasoning="Teams played close game",
                    suggested_tags=["rivalry"],
                ),
            ],
            reasoning="Selected based on prompt",
        )
        assert len(ctx.relevant_storyline_ids) == 2
        assert len(ctx.new_storyline_candidates) == 1
        assert ctx.new_storyline_candidates[0].suggested_headline == "New Rivalry"


class TestStorylineCandidateSchema:
    def test_minimal(self):
        c = StorylineCandidate(suggested_headline="Test", reasoning="Because")
        assert c.suggested_tags == []

    def test_with_tags(self):
        c = StorylineCandidate(
            suggested_headline="Test",
            reasoning="Because",
            suggested_tags=["streak", "trade"],
        )
        assert c.suggested_tags == ["streak", "trade"]


class TestBuildUserPrompt:
    def test_includes_config_and_storylines(self):
        config = ReportConfig(
            time_range=TimeRange.single_week(8),
            voice="snarky columnist",
            focus_hints=["upsets", "trades"],
            focus_teams=["Team Taco"],
            custom_instructions="Roast the losers",
        )
        summaries = [
            {
                "id": "story_1",
                "headline": "Win Streak",
                "summary": "Team is on fire",
                "status": "active",
                "priority": 1,
                "tags": ["streak"],
                "team_ids": [3],
            },
        ]

        prompt = StorylineCurator._build_user_prompt(config, summaries)

        assert "**Week(s):** 8" in prompt
        assert "snarky columnist" in prompt
        assert "upsets, trades" in prompt
        assert "Team Taco" in prompt
        assert "Roast the losers" in prompt
        assert "[story_1]" in prompt
        assert "Win Streak" in prompt
        assert "Team is on fire" in prompt
        assert "Tags: streak" in prompt

    def test_multi_week_range(self):
        config = ReportConfig(time_range=TimeRange.range(5, 8))
        prompt = StorylineCurator._build_user_prompt(config, [])
        assert "**Week(s):** 5-8" in prompt


class TestBuildUserPromptWithData:
    def _sample_week_data(self) -> dict:
        return {
            "games": [
                {
                    "team_a": "Team Taco",
                    "team_b": "The Waiver Wire",
                    "points_a": 142.3,
                    "points_b": 98.7,
                    "winner": "Team Taco",
                },
            ],
            "standings": {
                "found": True,
                "as_of_week": 8,
                "standings": [
                    {
                        "team_name": "Team Taco",
                        "wins": 7,
                        "losses": 1,
                        "record": "7-1",
                        "points_for": 1204.5,
                        "rank": 1,
                    },
                ],
            },
            "top_performers": [
                {
                    "rank": 1,
                    "player_name": "Patrick Mahomes",
                    "position": "QB",
                    "team_name": "Team Taco",
                    "points": 38.7,
                },
            ],
            "transactions": [
                {
                    "type": "trade",
                    "details": [
                        {"team_name": "Team Taco", "assets_received": []},
                        {"team_name": "The Waiver Wire", "assets_received": []},
                    ],
                },
                {
                    "type": "waiver",
                    "details": [
                        {
                            "team_name": "Team Taco",
                            "assets_received": [
                                {"asset_type": "player", "player_name": "Derrick Henry", "position": "RB"},
                            ],
                        },
                    ],
                },
            ],
        }

    def test_includes_all_data_sections(self):
        config = ReportConfig(time_range=TimeRange.single_week(8))
        week_data = self._sample_week_data()

        prompt = StorylineCurator._build_user_prompt(config, [], week_data=week_data)

        assert "## This Week's Data" in prompt
        assert "### Scores" in prompt
        assert "Team Taco 142.3 vs The Waiver Wire 98.7" in prompt
        assert "### Standings" in prompt
        assert "1. Team Taco (7-1, 1204.5 PF)" in prompt
        assert "### Top Performers" in prompt
        assert "Patrick Mahomes (QB, Team Taco): 38.7 pts" in prompt
        assert "### Transactions" in prompt
        assert "trade: Team Taco \u2194 The Waiver Wire" in prompt
        assert "waiver: Team Taco added Derrick Henry" in prompt

    def test_omits_data_section_when_none(self):
        config = ReportConfig(time_range=TimeRange.single_week(8))

        prompt = StorylineCurator._build_user_prompt(config, [], week_data=None)

        assert "## This Week's Data" not in prompt


class TestFormatWeekData:
    def test_full_data(self):
        week_data = {
            "games": [
                {
                    "team_a": "Team A",
                    "team_b": "Team B",
                    "points_a": 120.0,
                    "points_b": 95.5,
                    "winner": "Team A",
                },
            ],
            "standings": {
                "found": True,
                "standings": [
                    {
                        "team_name": "Team A",
                        "wins": 6,
                        "losses": 2,
                        "record": "6-2",
                        "points_for": 980.3,
                        "rank": 2,
                    },
                ],
            },
            "top_performers": [
                {
                    "rank": 1,
                    "player_name": "Josh Allen",
                    "position": "QB",
                    "team_name": "Team A",
                    "points": 35.2,
                },
            ],
            "transactions": [
                {
                    "type": "free_agent",
                    "details": [
                        {
                            "team_name": "Team B",
                            "assets_received": [
                                {"asset_type": "player", "player_name": "Kicker Guy", "position": "K"},
                            ],
                        },
                    ],
                },
            ],
        }

        result = StorylineCurator._format_week_data(week_data)

        assert "### Scores" in result
        assert "### Standings" in result
        assert "### Top Performers" in result
        assert "### Transactions" in result
        assert "Team A 120.0 vs Team B 95.5 (winner: Team A)" in result
        assert "2. Team A (6-2, 980.3 PF)" in result
        assert "Josh Allen (QB, Team A): 35.2 pts" in result
        assert "free_agent: Team B added Kicker Guy" in result

    def test_empty_games_omits_scores(self):
        week_data = {
            "games": [],
            "standings": {
                "found": True,
                "standings": [
                    {
                        "team_name": "Team A",
                        "wins": 3,
                        "losses": 5,
                        "record": "3-5",
                        "points_for": 700.0,
                        "rank": 5,
                    },
                ],
            },
            "top_performers": [],
            "transactions": [],
        }

        result = StorylineCurator._format_week_data(week_data)

        assert "### Scores" not in result
        assert "### Standings" in result
        assert "### Top Performers" not in result
        assert "### Transactions" not in result

    def test_empty_dict_returns_empty(self):
        assert StorylineCurator._format_week_data({}) == ""

    def test_none_returns_empty(self):
        assert StorylineCurator._format_week_data(None) == ""

    def test_score_line_format(self):
        week_data = {
            "games": [
                {
                    "team_a": "X",
                    "team_b": "Y",
                    "points_a": 100.0,
                    "points_b": 50.0,
                    "winner": "X",
                },
            ],
        }
        result = StorylineCurator._format_week_data(week_data)
        assert "- X 100.0 vs Y 50.0 (winner: X)" in result


class TestCurateEarlyReturn:
    @pytest.mark.anyio
    async def test_no_summaries_no_data_returns_early(self):
        curator = StorylineCurator(model="gpt-5-mini")
        config = ReportConfig(time_range=TimeRange.single_week(8))

        result = await curator.curate(config, [])

        assert result.relevant_storyline_ids == []
        assert result.new_storyline_candidates == []
        assert result.reasoning == "No storylines or week data to curate."

    @pytest.mark.anyio
    async def test_no_summaries_with_data_calls_llm(self):
        expected = CuratedContext(
            relevant_storyline_ids=[],
            new_storyline_candidates=[
                StorylineCandidate(
                    suggested_headline="Blowout Win",
                    reasoning="Team Taco scored 142",
                ),
            ],
            reasoning="Found blowout from game data",
        )

        mock_result = MagicMock()
        mock_result.final_output = expected

        with patch("reporter.agent.curator.Runner") as MockRunner:
            MockRunner.run = AsyncMock(return_value=mock_result)

            curator = StorylineCurator(model="gpt-5-mini")
            config = ReportConfig(time_range=TimeRange.single_week(8))
            week_data = {
                "games": [
                    {
                        "team_a": "Team Taco",
                        "team_b": "Wire",
                        "points_a": 142.0,
                        "points_b": 90.0,
                        "winner": "Team Taco",
                    },
                ],
                "standings": {"found": True, "standings": []},
                "top_performers": [],
                "transactions": [],
            }

            result = await curator.curate(config, [], week_data=week_data)

        assert len(result.new_storyline_candidates) == 1
        assert result.new_storyline_candidates[0].suggested_headline == "Blowout Win"
        MockRunner.run.assert_called_once()


class TestCurateWithMock:
    @pytest.mark.anyio
    async def test_returns_curated_context(self):
        expected = CuratedContext(
            relevant_storyline_ids=["story_1"],
            new_storyline_candidates=[
                StorylineCandidate(
                    suggested_headline="New Arc",
                    reasoning="Looks promising",
                ),
            ],
            reasoning="Selected story_1 because relevant",
        )

        mock_result = MagicMock()
        mock_result.final_output = expected

        with patch("reporter.agent.curator.Runner") as MockRunner:
            MockRunner.run = AsyncMock(return_value=mock_result)

            curator = StorylineCurator(model="gpt-5-mini")
            config = ReportConfig(
                time_range=TimeRange.single_week(8),
                custom_instructions="weekly recap",
            )
            summaries = [
                {
                    "id": "story_1",
                    "headline": "Test",
                    "summary": "Sum",
                    "status": "active",
                    "priority": 1,
                    "tags": [],
                    "team_ids": [],
                },
            ]

            result = await curator.curate(config, summaries)

        assert result.relevant_storyline_ids == ["story_1"]
        assert len(result.new_storyline_candidates) == 1
        assert result.reasoning == "Selected story_1 because relevant"
