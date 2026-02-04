"""Tests for ReportSpec and related models."""

import pytest
from agent.specs import (
    ReportSpec,
    ArticleRequest,
    ArticleType,
    TimeRange,
    ToneControls,
    BiasProfile,
    get_preset,
    PRESETS,
)


class TestTimeRange:
    def test_single_week(self):
        tr = TimeRange.single_week(8)
        assert tr.week_start == 8
        assert tr.week_end == 8

    def test_range(self):
        tr = TimeRange.range(5, 10)
        assert tr.week_start == 5
        assert tr.week_end == 10


class TestToneControls:
    def test_defaults(self):
        tone = ToneControls()
        assert tone.snark_level == 1
        assert tone.hype_level == 1
        assert tone.seriousness == 1

    def test_validation(self):
        with pytest.raises(ValueError):
            ToneControls(snark_level=5)  # Max is 3


class TestBiasProfile:
    def test_defaults(self):
        bias = BiasProfile()
        assert bias.favored_teams == []
        assert bias.disfavored_teams == []
        assert bias.intensity == 1

    def test_with_teams(self):
        bias = BiasProfile(
            favored_teams=["Team Taco"],
            disfavored_teams=["The Waiver Wire"],
            intensity=2,
        )
        assert "Team Taco" in bias.favored_teams
        assert "The Waiver Wire" in bias.disfavored_teams


class TestReportSpec:
    def test_from_dict(self, sample_spec_dict):
        spec = ReportSpec.model_validate(sample_spec_dict)
        assert spec.article_type == ArticleType.WEEKLY_RECAP
        assert spec.time_range.week_start == 8
        assert spec.length_target == 1000

    def test_is_complete(self, sample_spec_dict):
        spec = ReportSpec.model_validate(sample_spec_dict)
        assert spec.is_complete()

    def test_defaults(self):
        spec = ReportSpec(
            article_type=ArticleType.WEEKLY_RECAP,
            time_range=TimeRange.single_week(8),
        )
        assert spec.genre_voice == "sports columnist"
        assert spec.length_target == 1000


class TestPresets:
    def test_all_presets_exist(self):
        expected = ["weekly_recap", "power_rankings", "team_deep_dive", "playoff_reaction"]
        for name in expected:
            assert name in PRESETS
            preset = get_preset(name)
            assert preset is not None
            assert preset.is_complete() or preset.time_range is not None

    def test_weekly_recap_preset(self):
        preset = get_preset("weekly_recap")
        assert preset.article_type == ArticleType.WEEKLY_RECAP
        assert len(preset.structure.sections) > 0

    def test_power_rankings_preset(self):
        preset = get_preset("power_rankings")
        assert preset.article_type == ArticleType.POWER_RANKINGS


class TestArticleRequest:
    def test_basic_request(self):
        request = ArticleRequest(
            raw_request="Weekly recap for week 8",
            preset="weekly_recap",
            week=8,
        )
        assert request.week == 8
        assert request.preset == "weekly_recap"

    def test_with_overrides(self):
        request = ArticleRequest(
            raw_request="Snarky recap",
            week=8,
            overrides={"tone_controls": {"snark_level": 3}},
        )
        assert request.overrides["tone_controls"]["snark_level"] == 3
