"""Compact fact inputs from real frozen-query adapter output, without model calls."""

from __future__ import annotations

from dataclasses import replace
import json

import pytest

from backend.services.datalayer import FrozenLeagueData
from backend.services.reporter.runner.research_brief import BriefFact
from backend.services.reporter.runner.tools.brief_tools import BRIEF_TOOL_SPECS, save_fact
from backend.tests.services.datalayer.test_frozen_query_runtime import (
    _mutated_copy_many, ready_snapshot,
)
from backend.tests.services.reporter.test_executed_evidence import execute, setup


def selection(record, field):
    return {"ref": record.ref, "field": field, "value": record.fields[field]}


def test_public_save_fact_schema_only_requests_selected_values() -> None:
    schema = next(spec["function"]["parameters"] for spec in BRIEF_TOOL_SPECS if spec["function"]["name"] == "save_fact")
    assert schema["required"] == ["id", "claim_text", "bindings"]
    assert {"data_refs", "numbers"}.isdisjoint(schema["properties"])
    binding = schema["properties"]["bindings"]["items"]
    assert set(binding["properties"]) == {"ref", "field", "value"}
    assert binding["required"] == ["ref", "field", "value"]
    assert binding["additionalProperties"] is False


def test_binding_repairs_are_exact_bounded_and_do_not_mutate(ready_snapshot) -> None:
    with FrozenLeagueData.open(ready_snapshot) as data:
        registry, ctx = setup(data)
        _, records = execute(registry, ctx, "standings", week=2)
        team = next(record for record in records if "wins" in record.fields)
        bounded = replace(team, ref="bounded.r0", source="bounded", fields={**team.fields, **{f"metric_{i}": i for i in range(30)}})
        unrelated = replace(team, ref="bounded.r1", source="bounded", fields={"unrelated_catalog_field": 1})
        ctx.evidence.register("bounded", (bounded, unrelated))

        def rejected(change):
            result = json.loads(save_fact(ctx, id="fact_repair", claim_text="A source observation.", bindings=[selection(bounded, "wins") | change]))
            assert not result["ok"]
            assert ctx.brief.brief.revision == 0
            assert ctx.brief.brief.get_fact("fact_repair") is None
            return result["error"]

        wrong_field = rejected({"field": "invented"})
        assert wrong_field["available_fields"] == list(bounded.fields)[:12]
        assert wrong_field["fields_truncated"]
        assert "unrelated_catalog_field" not in json.dumps(wrong_field)
        assert wrong_field["repair"]["action"] == "select_executed_field"
        wrong_value = rejected({"value": -999})
        assert wrong_value["expected_value"] == bounded.fields["wins"]
        assert wrong_value["repair"]["action"] == "match_executed_value"
        wrong_subject = rejected({"subject": "Different Team"})
        assert wrong_subject["expected_value"] == bounded.subject
        assert wrong_subject["repair"]["action"] == "use_compact_binding"
        unknown = rejected({"ref": "never_executed.r0"})
        assert unknown["outcome"] == "unknown_reference"
        assert "available_fields" not in unknown
        assert unknown["repair"]["action"] == "select_available_evidence"


def test_actual_compact_fact_derives_context_refs_and_numeric_summary(ready_snapshot) -> None:
    with FrozenLeagueData.open(ready_snapshot) as data:
        registry, ctx = setup(data)
        _, records = execute(registry, ctx, "standings", week=2)
        team = next(record for record in records if "wins" in record.fields)
        compact = selection(team, "wins")
        result = json.loads(save_fact(ctx, id="fact_wins", claim_text="The team's recorded win total.", bindings=[compact]))
        assert result["ok"], result
        saved = ctx.brief.brief.get_fact("fact_wins")
        assert saved.data_refs == (team.ref,)
        assert saved.numbers == {"wins": team.fields["wins"]}
        for dimension in ("subject", "season", "week_from", "week_to", "perspective"):
            assert getattr(saved.bindings[0], dimension) == getattr(team, dimension)
        with pytest.raises(ValueError):
            saved.bindings[0].subject = "A different team"
        assert BriefFact.model_validate(saved.model_dump()) == saved

        # Redundant references and model-generated numeric aliases no longer cause retries.
        legacy = json.loads(save_fact(
            ctx, id="fact_wins", claim_text="The team's recorded win total.", bindings=[compact, compact],
            data_refs=[team.ref, records[0].ref, "standings:week=2"],
            numbers={"team_wins_after_week_2": team.fields["wins"]},
        ))
        assert legacy["ok"] and not legacy["changed"]
        assert ctx.brief.brief.get_fact("fact_wins") == saved


@pytest.mark.parametrize("change", [
    {"value": -1000}, {"field": "imaginary_metric"}, {"ref": "e999_0.r0"},
    {"subject": "Wrong Team"}, {"season": 1900}, {"week_from": 1000},
    {"week_to": 1000}, {"perspective": "received"},
])
def test_actual_compact_selection_rejects_value_or_legacy_attribution_mismatch(ready_snapshot, change) -> None:
    with FrozenLeagueData.open(ready_snapshot) as data:
        registry, ctx = setup(data)
        _, records = execute(registry, ctx, "standings", week=2)
        team = next(record for record in records if "wins" in record.fields)
        result = json.loads(save_fact(ctx, id="bad_fact", claim_text="Incorrect support.", bindings=[selection(team, "wins") | change]))
        assert not result["ok"]
        assert result["error"]["code"] == "unsupported_fact"
        assert ctx.brief.brief.revision == 0


def test_unavailable_selected_source_still_rejected(ready_snapshot) -> None:
    with FrozenLeagueData.open(ready_snapshot) as data:
        registry, ctx = setup(data)
        _, records = execute(registry, ctx, "standings", week=2)
        team = next(record for record in records if "wins" in record.fields)
        absent = replace(team, ref="unavailable.r0", source="unavailable", outcome="unavailable")
        ctx.evidence.register(absent.source, (absent,))
        result = json.loads(save_fact(ctx, id="bad_fact", claim_text="Unavailable support.", bindings=[selection(absent, "wins")]))
        assert not result["ok"]
        assert result["error"]["code"] == "unsupported_fact"


def test_numeric_summary_keeps_same_metric_attributed_to_distinct_records(ready_snapshot) -> None:
    with FrozenLeagueData.open(ready_snapshot) as data:
        registry, ctx = setup(data)
        _, records = execute(registry, ctx, "standings", week=2)
        teams = [record for record in records if "wins" in record.fields]
        assert len(teams) > 1
        result = json.loads(save_fact(ctx, id="fact_records", claim_text="The teams' recorded wins.", bindings=[selection(team, "wins") for team in teams]))
        assert result["ok"]
        assert ctx.brief.brief.get_fact("fact_records").numbers == {f"{team.ref}.wins": team.fields["wins"] for team in teams}


def test_actual_superlative_selects_asserted_metric_and_keeps_context(ready_snapshot) -> None:
    with FrozenLeagueData.open(ready_snapshot) as data:
        registry, ctx = setup(data)
        _, records = execute(registry, ctx, "standings", week=2)
        teams = [record for record in records if "points_for" in record.fields]
        leader = max(teams, key=lambda record: record.fields["points_for"])
        result = json.loads(save_fact(
            ctx, id="fact_highest_points", claim_text="Highest recorded points, with team and rank context.",
            bindings=[selection(leader, field) for field in ("points_for", "team_name", "rank")],
            category="superlative", superlative_direction="max",
            superlative_binding={"ref": leader.ref, "field": "points_for"},
        ))
        assert result["ok"], result
        assert len(ctx.brief.brief.get_fact("fact_highest_points").bindings) == 3
        wrong_selector = json.loads(save_fact(
            ctx, id="bad_metric", claim_text="Unknown asserted metric.",
            bindings=[selection(leader, "points_for")], category="superlative", superlative_direction="max",
            superlative_binding={"ref": leader.ref, "field": "rank"},
        ))
        assert not wrong_selector["ok"]


@pytest.mark.parametrize("partial, unique", [(True, False), (False, True)])
def test_selected_superlative_metric_retains_population_and_tie_requirements(ready_snapshot, partial, unique) -> None:
    with FrozenLeagueData.open(ready_snapshot) as data:
        registry, ctx = setup(data)
        _, records = execute(registry, ctx, "standings", week=2)
        original = next(record for record in records if "points_for" in record.fields)
        leader = replace(original, source="comparison", ref="comparison.r0", population="comparison:teams", complete=not partial)
        tied = replace(leader, ref="comparison.r1", subject="Other Team")
        ctx.evidence.register("comparison", (leader, tied))
        result = json.loads(save_fact(
            ctx, id="unsupported_extreme", claim_text="A unique complete-population extreme.",
            bindings=[selection(leader, "points_for"), selection(leader, "team_name")],
            category="superlative", superlative_direction="max", superlative_unique=unique,
            superlative_binding={"ref": leader.ref, "field": "points_for"},
        ))
        assert not result["ok"]
        assert ("complete" if partial else "tied") in result["error"]["message"]


def test_actual_week_two_score_winner_record_shape_normalizes_aliases(ready_snapshot) -> None:
    with FrozenLeagueData.open(ready_snapshot) as data:
        registry, ctx = setup(data)
        _, games = execute(registry, ctx, "week_games", week=2)
        _, standings = execute(registry, ctx, "standings", week=2)
        points_a = next(record for record in games if "points_a" in record.fields)
        points_b = next(record for record in games if "points_b" in record.fields)
        winner = next(record for record in games if "winner" in record.fields)
        standing = next(record for record in standings if "record" in record.fields)
        result = json.loads(save_fact(
            ctx, id="fact_week_two", claim_text="The matchup score and the recorded standings cutoff.",
            category="score",
            bindings=[selection(points_a, "points_a"), selection(points_b, "points_b"), selection(winner, "winner"), selection(standing, "record")],
            data_refs=[games[0].ref, points_a.ref, points_b.ref, winner.ref, standing.ref],
            numbers={"week_points": points_a.fields["points_a"], "opponent_points": points_b.fields["points_b"], "wins": standing.fields["wins"]},
        ))
        assert result["ok"], result
        saved = ctx.brief.brief.get_fact("fact_week_two")
        assert saved.numbers == {"points_a": points_a.fields["points_a"], "points_b": points_b.fields["points_b"]}
        assert saved.bindings[-1].value == standing.fields["record"]


def test_actual_compact_binding_preserves_exact_emoji_identity_without_copying(ready_snapshot, tmp_path) -> None:
    source_name = "FANTASY IS LUCK\U0001f92c\U0001f92c\U0001f92c"
    copied_name = "FANTASY IS LUCK\U0001f92a\U0001f92a\U0001f92a"
    changed = _mutated_copy_many(
        ready_snapshot.artifact.path, tmp_path / "compact-identity.sqlite",
        (("UPDATE team_profiles SET team_name=? WHERE roster_id=1", (source_name,)),),
    )
    with FrozenLeagueData.open(ready_snapshot.model_copy(update={"artifact": changed})) as data:
        registry, ctx = setup(data)
        _, records = execute(registry, ctx, "standings", week=2)
        team = next(record for record in records if record.subject == source_name and "wins" in record.fields)
        compact = selection(team, "wins")
        accepted = json.loads(save_fact(ctx, id="fact_exact_name", claim_text="The source team's win total.", bindings=[compact]))
        assert accepted["ok"]
        assert ctx.brief.brief.get_fact("fact_exact_name").bindings[0].subject == source_name
        rejected = json.loads(save_fact(ctx, id="fact_wrong_name", claim_text="Wrong copied identity.", bindings=[compact | {"subject": copied_name}]))
        assert not rejected["ok"]
        assert "wrong subject" in rejected["error"]["message"]
