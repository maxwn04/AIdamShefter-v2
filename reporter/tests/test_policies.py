"""Tests for policies module."""

import pytest
from reporter.agent.policies import (
    check_fact_grounding,
    get_bias_framing_rules,
    validate_tool_call_phase,
    extract_numbers_from_text,
)
from reporter.agent.config import (
    ReportConfig,
    TimeRange,
    BiasProfile,
)
from reporter.agent.schemas import ReportBrief, Fact, BriefMeta, ResolvedStyle, ResolvedBias


@pytest.fixture
def sample_brief():
    return ReportBrief(
        meta=BriefMeta(
            league_name="Test League",
            league_id="12345",
            week_start=8,
            week_end=8,
            article_type="weekly_recap",
        ),
        facts=[
            Fact(
                id="fact_001",
                claim_text="Team scored 142.3 points",
                numbers={"points": 142.3, "wins": 7},
            )
        ],
        storylines=[],
        outline=[],
        style=ResolvedStyle(voice="columnist"),
        bias=ResolvedBias(),
    )


class TestCheckFactGrounding:
    def test_grounded_claim(self, sample_brief):
        is_grounded, error = check_fact_grounding(
            claim="Team scored 142.3 points",
            numbers={"points": 142.3},
            brief=sample_brief,
            policy="strict",
        )
        assert is_grounded
        assert error is None

    def test_ungrounded_claim_strict(self, sample_brief):
        is_grounded, error = check_fact_grounding(
            claim="Team scored 150 points",
            numbers={"points": 150.0},
            brief=sample_brief,
            policy="strict",
        )
        assert not is_grounded
        assert "150" in error

    def test_relaxed_policy_allows_minor_numbers(self, sample_brief):
        # Relaxed policy only checks major keys
        is_grounded, error = check_fact_grounding(
            claim="Some minor stat",
            numbers={"minor_stat": 999.0},
            brief=sample_brief,
            policy="relaxed",
        )
        assert is_grounded


class TestGetBiasFramingRules:
    def test_no_bias(self):
        config = ReportConfig(
            time_range=TimeRange.single_week(8),
            bias_profile=None,
        )
        rules = get_bias_framing_rules(config)
        assert rules == []

    def test_zero_intensity(self):
        config = ReportConfig(
            time_range=TimeRange.single_week(8),
            bias_profile=BiasProfile(
                favored_teams=["Team Taco"],
                intensity=0,
            ),
        )
        rules = get_bias_framing_rules(config)
        assert rules == []

    def test_favored_team_rules(self):
        config = ReportConfig(
            time_range=TimeRange.single_week(8),
            bias_profile=BiasProfile(
                favored_teams=["Team Taco"],
                intensity=2,
            ),
        )
        rules = get_bias_framing_rules(config)
        assert len(rules) > 0
        assert any("Team Taco" in rule for rule in rules)
        # Should always include the boundary rule
        assert any("NEVER change" in rule for rule in rules)

    def test_disfavored_team_rules(self):
        config = ReportConfig(
            time_range=TimeRange.single_week(8),
            bias_profile=BiasProfile(
                disfavored_teams=["The Waiver Wire"],
                intensity=3,
            ),
        )
        rules = get_bias_framing_rules(config)
        assert any("The Waiver Wire" in rule for rule in rules)


class TestValidateToolCallPhase:
    def test_research_phase_allows_all(self):
        is_allowed, error = validate_tool_call_phase("league_snapshot", "research")
        assert is_allowed
        assert error is None

    def test_draft_phase_blocks_all(self):
        is_allowed, error = validate_tool_call_phase("league_snapshot", "draft")
        assert not is_allowed
        assert "drafting" in error.lower()

    def test_verify_phase_limited_tools(self):
        # Allowed
        is_allowed, _ = validate_tool_call_phase("run_sql", "verify")
        assert is_allowed

        # Not allowed
        is_allowed, error = validate_tool_call_phase("team_dossier", "verify")
        assert not is_allowed


class TestExtractNumbersFromText:
    def test_extract_scores(self):
        text = "Team Taco won 142.3-98.7 in a dominant performance."
        numbers = extract_numbers_from_text(text)
        assert any(v == 142.3 for v in numbers.values())
        assert any(v == 98.7 for v in numbers.values())

    def test_extract_points(self):
        text = "Josh Allen scored 38.2 points this week."
        numbers = extract_numbers_from_text(text)
        assert any(v == 38.2 for v in numbers.values())

    def test_extract_record(self):
        text = "Team Taco (7-1) continues their winning ways."
        numbers = extract_numbers_from_text(text)
        assert any(v == 7.0 for v in numbers.values())
        assert any(v == 1.0 for v in numbers.values())
