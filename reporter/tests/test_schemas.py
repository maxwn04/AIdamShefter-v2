"""Tests for ReportBrief and related schemas."""

import pytest
from reporter.agent.schemas import (
    ReportBrief,
    Fact,
    Storyline,
    Section,
    BriefMeta,
    ResolvedStyle,
    ResolvedBias,
    ArticleOutput,
    VerificationResult,
    ClaimMismatch,
)
from reporter.agent.specs import ReportSpec, ArticleType, TimeRange

# Rebuild models to resolve forward references
ArticleOutput.model_rebuild()


class TestFact:
    def test_basic_fact(self):
        fact = Fact(
            id="fact_001",
            claim_text="Team Taco scored 142.3 points",
            data_refs=["get_week_games:week=8"],
            numbers={"points": 142.3},
            category="score",
        )
        assert fact.id == "fact_001"
        assert fact.numbers["points"] == 142.3

    def test_fact_defaults(self):
        fact = Fact(
            id="fact_002",
            claim_text="Something happened",
        )
        assert fact.category == "general"
        assert fact.data_refs == []
        assert fact.numbers == {}


class TestStoryline:
    def test_basic_storyline(self):
        storyline = Storyline(
            id="story_001",
            headline="Upset Alert",
            summary="The underdog pulled off an upset.",
            supporting_fact_ids=["fact_001", "fact_002"],
            priority=1,
        )
        assert storyline.priority == 1
        assert len(storyline.supporting_fact_ids) == 2


class TestReportBrief:
    def test_from_dict(self, sample_brief_dict):
        brief = ReportBrief.model_validate(sample_brief_dict)
        assert brief.meta.league_name == "Test League"
        assert len(brief.facts) == 2
        assert len(brief.storylines) == 1

    def test_get_fact(self, sample_brief_dict):
        brief = ReportBrief.model_validate(sample_brief_dict)
        fact = brief.get_fact("fact_001")
        assert fact is not None
        assert fact.claim_text == "Team Taco defeated The Waiver Wire 142.3-98.7"

        missing = brief.get_fact("nonexistent")
        assert missing is None

    def test_get_facts_by_category(self, sample_brief_dict):
        brief = ReportBrief.model_validate(sample_brief_dict)
        score_facts = brief.get_facts_by_category("score")
        assert len(score_facts) == 1
        assert score_facts[0].id == "fact_001"

    def test_get_lead_storylines(self, sample_brief_dict):
        brief = ReportBrief.model_validate(sample_brief_dict)
        leads = brief.get_lead_storylines(max_priority=1)
        assert len(leads) == 1
        assert leads[0].headline == "Taco Tuesday Massacre"


class TestVerificationResult:
    def test_passed_verification(self):
        result = VerificationResult(
            passed=True,
            claims_checked=10,
            claims_matched=10,
            mismatches=[],
            corrections_made=[],
        )
        assert result.passed

    def test_failed_verification(self):
        mismatch = ClaimMismatch(
            claim_text="Team Taco scored 145 points",
            expected_value="142.3",
            actual_value="145",
            fact_id="fact_001",
            severity="error",
        )
        result = VerificationResult(
            passed=False,
            claims_checked=10,
            claims_matched=9,
            mismatches=[mismatch],
            corrections_made=[],
        )
        assert not result.passed
        assert len(result.mismatches) == 1


class TestArticleOutput:
    def test_basic_output(self, sample_brief_dict, sample_spec_dict):
        brief = ReportBrief.model_validate(sample_brief_dict)
        spec = ReportSpec.model_validate(sample_spec_dict)

        output = ArticleOutput(
            article="# Week 8 Recap\n\nContent here...",
            spec=spec,
            brief=brief,
        )
        assert output.article.startswith("# Week 8")
        assert output.trace_id is None
        assert output.generated_at is not None
