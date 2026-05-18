"""Tests for reporter v2 schemas and state containers."""

import pytest
from pydantic import ValidationError

from reporter_v2.runner.schemas import (
    Article,
    ArticleOutput,
    Fact,
    ReportBrief,
    Storyline,
)
from reporter_v2.runner.state import ArtifactStore, ProcedureState, RunnerConfig


class TestFact:
    def test_basic_fact(self):
        fact = Fact(
            id="fact_001",
            claim_text="Team Taco scored 142.3 points",
            data_refs=["week_games:week=8"],
            numbers={"points": 142.3},
            category="score",
        )

        assert fact.id == "fact_001"
        assert fact.claim_text == "Team Taco scored 142.3 points"
        assert fact.data_refs == ["week_games:week=8"]
        assert fact.numbers["points"] == 142.3
        assert fact.category == "score"

    def test_fact_defaults(self):
        fact = Fact(id="fact_002", claim_text="Something happened")

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
            revision_at_set=3,
        )

        assert storyline.priority == 1
        assert storyline.revision_at_set == 3
        assert len(storyline.supporting_fact_ids) == 2

    @pytest.mark.parametrize("priority", [0, 6])
    def test_priority_bounds(self, priority):
        with pytest.raises(ValidationError):
            Storyline(
                id="story_001",
                headline="Invalid Priority",
                summary="This priority is outside the allowed range.",
                priority=priority,
            )


class TestReportBrief:
    def test_from_dict(self, sample_v2_brief_dict):
        brief = ReportBrief.model_validate(sample_v2_brief_dict)

        assert brief.revision == 2
        assert brief.meta.league_name == "Test League"
        assert len(brief.facts) == 2
        assert len(brief.storylines) == 1
        assert len(brief.outline.sections) == 1

    def test_get_fact(self, sample_v2_brief_dict):
        brief = ReportBrief.model_validate(sample_v2_brief_dict)

        fact = brief.get_fact("fact_001")
        assert fact is not None
        assert fact.claim_text == "Team Taco defeated The Waiver Wire 142.3-98.7"
        assert brief.get_fact("nonexistent") is None

    def test_bump_revision(self):
        brief = ReportBrief()

        assert brief.revision == 0
        assert brief.bump_revision() == 1
        assert brief.revision == 1

    def test_staleness_info_empty_when_artifacts_are_current(
        self, sample_v2_brief_dict
    ):
        brief = ReportBrief.model_validate(sample_v2_brief_dict)

        assert brief.staleness_info() == {}

    def test_staleness_info_reports_stale_outline_and_storylines(
        self, sample_v2_brief_dict
    ):
        brief = ReportBrief.model_validate(sample_v2_brief_dict)
        brief.bump_revision()

        assert brief.staleness_info() == {
            "outline_stale": True,
            "outline_gap": "1 mutation(s) since outline was set",
            "stale_storyline_ids": ["story_001"],
        }

    def test_staleness_info_skips_empty_outline(self):
        brief = ReportBrief(revision=2)

        assert brief.staleness_info() == {}


class TestArticle:
    def test_set_and_get_section(self):
        article = Article()

        article.set_section("opening", "# Opening\n\nHello.")
        section = article.get_section("opening")

        assert section is not None
        assert section.content == "# Opening\n\nHello."
        assert article.section_order == ["opening"]

    def test_set_section_updates_existing_without_duplicate_order(self):
        article = Article()

        article.set_section("opening", "First draft")
        article.set_section("opening", "Second draft")

        assert len(article.sections) == 1
        assert article.get_section("opening").content == "Second draft"
        assert article.section_order == ["opening"]

    def test_to_markdown_uses_section_order(self):
        article = Article()
        article.set_section("opening", "# Opening")
        article.set_section("closing", "# Closing")
        article.section_order = ["closing", "opening"]

        assert article.to_markdown() == "# Closing\n\n# Opening"

    def test_to_markdown_uses_section_list_when_order_empty(self):
        article = Article()
        article.set_section("opening", "# Opening")
        article.set_section("closing", "# Closing")
        article.section_order = []

        assert article.to_markdown() == "# Opening\n\n# Closing"


class TestArticleOutput:
    def test_roundtrip_serialization(self, sample_v2_brief_dict):
        brief = ReportBrief.model_validate(sample_v2_brief_dict)
        output = ArticleOutput(
            article="# Week 8 Recap\n\nContent here...",
            brief=brief,
            run_log_summary={"tool_calls": 3},
        )

        roundtripped = ArticleOutput.model_validate(output.model_dump())

        assert roundtripped.article.startswith("# Week 8")
        assert roundtripped.brief.meta.league_name == "Test League"
        assert roundtripped.run_log_summary == {"tool_calls": 3}
        assert roundtripped.generated_at is not None


class TestRunnerState:
    def test_artifact_store_defaults(self):
        store = ArtifactStore()

        assert isinstance(store.brief, ReportBrief)
        assert isinstance(store.article, Article)

    def test_procedure_state_defaults(self):
        state = ProcedureState()

        assert state.active is None

    def test_runner_config_defaults(self):
        config = RunnerConfig()

        assert config.soft_tool_limit == 40
        assert config.hard_tool_limit == 50
        assert config.max_turns == 60
        assert config.model is None
