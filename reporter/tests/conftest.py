"""Shared fixtures for reporter tests."""

import pytest


@pytest.fixture
def sample_brief_dict():
    """Sample ReportBrief as a dictionary."""
    return {
        "meta": {
            "league_name": "Test League",
            "league_id": "12345",
            "week_start": 8,
            "week_end": 8,
            "article_type": "weekly_recap",
        },
        "facts": [
            {
                "id": "fact_001",
                "claim_text": "Team Taco defeated The Waiver Wire 142.3-98.7",
                "data_refs": ["week_games:week=8"],
                "numbers": {"team_score": 142.3, "opponent_score": 98.7},
                "category": "score",
            },
            {
                "id": "fact_002",
                "claim_text": "Team Taco is now 7-1",
                "data_refs": ["league_snapshot:week=8"],
                "numbers": {"wins": 7, "losses": 1},
                "category": "standing",
            },
        ],
        "storylines": [
            {
                "id": "story_001",
                "headline": "Taco Tuesday Massacre",
                "summary": "Team Taco dominated with a 43-point victory.",
                "supporting_fact_ids": ["fact_001"],
                "priority": 1,
                "tags": ["blowout"],
            }
        ],
        "outline": [
            {
                "title": "Introduction",
                "bullet_points": ["Hook with lead storyline"],
                "required_fact_ids": ["fact_001"],
                "storyline_ids": ["story_001"],
            }
        ],
        "style": {"voice": "sports columnist", "pacing": "moderate", "humor_level": 1, "formality": "casual"},
        "bias": {"favored_teams": [], "disfavored_teams": [], "intensity": 0, "framing_rules": []},
    }
