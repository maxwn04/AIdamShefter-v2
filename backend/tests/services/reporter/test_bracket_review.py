"""Recorded bracket outcomes remain distinct when a writer abandons fact binding."""

from dataclasses import replace

from backend.services.reporter.runner.draft_verification import verify_draft
from backend.services.reporter.runner.evidence import EvidenceCatalog
from backend.services.reporter.runner.research_brief import ResearchBrief
from backend.services.reporter.runner.state import ArtifactStore
from backend.services.reporter.runner.tools.evidence_presentation import evidence_page, selected_records


SEASONS = [{"role": "primary", "season_year": 2025, "through_week": 15, "competition_season_id": "season-2025"}]


def bracket_records():
    raw = {"found": True, "configured_playoff_teams": 6,
           "coverage": "visible_recorded_matchups", "remaining_field_status": "not_established",
           "observed_matchup_count": 2, "observed_participants": ["caydengu", "pookie", "mcleare", "Thought"],
           "brackets": {"losers": {"bracket_type": "losers", "rounds": {1: [
               {"bracket_type": "losers", "matchup_id": 1, "round": 1, "team_1": "caydengu", "team_2": "pookie",
                "winner": "pookie", "loser": "caydengu", "status": "complete"},
               {"bracket_type": "losers", "matchup_id": 2, "round": 1, "team_1": "mcleare", "team_2": "Thought",
                "winner": "Thought", "loser": "mcleare", "status": "complete"},
           ]}}}}
    return raw, selected_records("bracket", "playoff_bracket", raw, {}, SEASONS, lambda *_: (None, None))


def test_actual_losers_bracket_shape_keeps_recorded_outcomes_and_raw_paths():
    raw, records = bracket_records()
    matchups = [record for record in records if "recorded_winner" in record.fields]
    assert [record.fields["recorded_winner"] for record in matchups] == ["pookie", "Thought"]
    assert [record.fields["recorded_loser"] for record in matchups] == ["caydengu", "mcleare"]
    assert all(record.fields["result_kind"] == "recorded_bracket_outcome" for record in matchups)
    assert matchups[0].field_paths["recorded_winner"] == "/brackets/losers/rounds/1/0/winner"
    assert matchups[0].fields["winner"] == "pookie"  # Legacy bindings remain readable.
    assert "recorded_winner" not in raw["brackets"]["losers"]["rounds"][1][0]
    assert any("complete remaining playoff field" in line for line in evidence_page(records)["guidance"])


def test_score_winner_is_explicitly_a_different_evidence_kind():
    records = selected_records("games", "week_games", [{
        "week": 15, "team_a": "caydengu", "team_b": "pookie", "points_a": 156.58,
        "points_b": 131.00, "winner": "caydengu",
    }], {}, SEASONS, lambda *_: (None, None))
    outcome, = [record for record in records if "score_winner" in record.fields]
    assert outcome.fields["score_winner"] == "caydengu"
    assert outcome.fields["result_kind"] == "score_comparison"
    assert outcome.field_paths["score_winner"] == "/0/winner"
    assert "recorded_winner" not in outcome.fields


def test_advisory_reviews_executed_bracket_even_without_accepted_fact():
    _, records = bracket_records()
    catalog = EvidenceCatalog()
    catalog.register("bracket", records)
    artifact = ArtifactStore().create("article.md", "# Playoffs\n\nThe bracket lists mcleare and caydengu as its winners. Only those two remain.")
    receipt = verify_draft(artifact, ResearchBrief(), catalog)
    review = receipt.bracket_review
    assert review is not None
    assert [card.fields["recorded_winner"] for card in review.outcomes] == ["pookie", "Thought"]
    assert review.coverage[0].fields["configured_playoff_teams"] == 6
    assert review.coverage[0].fields["remaining_field_status"] == "not_established"
    assert any("Only those two remain" in passage for passage in review.passages)
    assert not receipt.as_dict()["submission_blocking"]
    assert not receipt.traceability_errors
    assert all(card.season == 2025 and card.week_to == 15 for card in review.outcomes)
    assert "not a prose mismatch verdict" in review.instruction


def test_catalog_tool_reads_are_defensive_and_review_ignores_other_tools():
    _, records = bracket_records()
    catalog = EvidenceCatalog()
    catalog.register("bracket", records)
    exposed = catalog.records_for_tool("playoff_bracket")
    exposed[0].fields["configured_playoff_teams"] = 2
    assert catalog.records_for_tool("playoff_bracket")[0].fields["configured_playoff_teams"] == 6
    other = EvidenceCatalog()
    other.register("bracket", tuple(replace(record, tool="unrelated") for record in records))
    artifact = ArtifactStore().create("article.md", "The playoff bracket has two winners.")
    assert verify_draft(artifact, ResearchBrief(), other).bracket_review is None


def test_legacy_pending_outcome_and_limited_source_stay_unknown():
    _, records = bracket_records()
    matchup = next(record for record in records if "recorded_winner" in record.fields)
    fields = {key: value for key, value in matchup.fields.items() if not key.startswith("recorded_")}
    fields.update(winner=None, loser=None, status="pending")
    pending = replace(matchup, fields=fields, limitations=("Later round pair omitted at cutoff.",))
    catalog = EvidenceCatalog()
    catalog.register("bracket", (pending,))
    review = verify_draft(ArtifactStore().create("article.md", "A playoff winner advances."), ResearchBrief(), catalog).bracket_review
    assert review.outcomes[0].fields["recorded_winner"] is None
    assert review.outcomes[0].limitations == pending.limitations
    assert not review.coverage  # No invented full-field or bye identity.
