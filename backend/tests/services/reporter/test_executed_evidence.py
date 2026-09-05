"""Real frozen SQLite -> adapter -> brief -> draft regressions; no paid calls."""

import asyncio
from dataclasses import asdict, replace
import json
from pathlib import Path

import pytest

from backend.services.datalayer import FrozenLeagueData
from backend.resources.reporting.tool_calls import FinishToolCall
from backend.services.reporter.runner.evidence import EvidenceRecord
from backend.services.reporter.runner.models import ToolCall
from backend.services.reporter.runner.runner import Runner
from backend.services.reporter.runner.tools.artifact_tools import (
    create_artifact, edit_artifact, submit_artifact, verify_artifact,
    register_artifact_tools,
)
from backend.services.reporter.runner.tools.brief_tools import save_fact, register_brief_tools
from backend.services.reporter.runner.tools.datalayer_tools import register_datalayer_tools
from backend.services.reporter.runner.tools.evidence_presentation import selected_records
from backend.services.reporter.runner.tools.registry import ToolRegistry
from backend.tests.services.datalayer.test_frozen_query_runtime import (
    ready_snapshot, v3_ready_snapshot, _mutated_copy_many,
)
from backend.tests.services.datalayer.test_frozen_query_history import _changed_franchise_artifact
from backend.tests.services.reporter.test_runner import RecordingProbe, make_response


def binding(record, field):
    return {
        "ref": record.ref, "field": field, "value": record.fields[field],
        **{key: getattr(record, key) for key in ("subject", "season", "week_from", "week_to", "perspective")},
    }


def setup(data):
    registry = ToolRegistry()
    register_datalayer_tools(registry, data)
    register_brief_tools(registry)
    register_artifact_tools(registry)
    runner = Runner(registry, complete=lambda **kwargs: None)
    return registry, runner.tool_context


def execute(registry, ctx, name, **kwargs):
    result = registry.get_handler(name)(**kwargs)
    return result, ctx.evidence.records_for(result.result["source"])


def save(ctx, record, field, category="general", **kwargs):
    return json.loads(save_fact(
        ctx, id=kwargs.pop("id", "fact_supported"), claim_text=kwargs.pop("claim_text", "Source-grounded observation."),
        data_refs=[record.ref], bindings=[binding(record, field)], category=category, **kwargs,
    ))


def test_actual_history_handles_have_canonical_identity_and_reach_rosters(v3_ready_snapshot, tmp_path):
    changed = _changed_franchise_artifact(v3_ready_snapshot, tmp_path)
    with FrozenLeagueData.open(v3_ready_snapshot.model_copy(update={"artifact": changed})) as data:
        registry, ctx = setup(data)
        result, records = execute(registry, ctx, "franchise_history", franchise_or_primary_roster="Current Guard")
        appearances = [r for r in records if "roster_lookup" in r.fields]
        assert [r.subject for r in appearances] == ["Old Guard", "Current Guard"]
        assert appearances[0].subject_id == appearances[1].subject_id
        assert appearances[0].subject_id is not None
        for appearance in appearances:
            roster, selected = execute(registry, ctx, "roster_at_cutoff", **appearance.fields["roster_lookup"])
            assert roster.metadata["raw_result"]["found"] is True
            assert any(r.subject_id == appearance.subject_id for r in selected)
        visible = json.dumps(result.result)
        assert "season_roster_id" not in visible and "competition_id" not in visible
        assert str(result.metadata["raw_result"]["franchise_id"]) not in visible
        assert result.metadata["identity_bindings"]


def test_actual_records_round_points_bind_team_and_reject_wrong_support(v3_ready_snapshot, tmp_path):
    changed = _mutated_copy_many(v3_ready_snapshot.artifact.path, tmp_path / "evidence-records.sqlite", (
        ("UPDATE standings SET wins=10, losses=18, points_for=1754.9999999999998, streak_len=14 WHERE league_id='league-2026' AND roster_id=1", ()),
        ("UPDATE standings SET wins=9, losses=19, streak_len=6 WHERE league_id='league-2026' AND roster_id=2", ()),
    ))
    with FrozenLeagueData.open(v3_ready_snapshot.model_copy(update={"artifact": changed})) as data:
        registry, ctx = setup(data)
        result, records = execute(registry, ctx, "standings", season=2026)
        teams = [r for r in records if "wins" in r.fields]
        first = next(r for r in teams if r.fields["wins"] == 10)
        assert first.fields["points_for"] == 1755.0
        shown = next(r for r in result.result["records"] if r["ref"] == first.ref)
        assert shown["display"]["points_for"] == "1755.00"
        assert save(ctx, first, "wins")["ok"]
        bad = binding(first, "wins") | {"subject": next(r.subject for r in teams if r.fields["wins"] == 9)}
        assert not json.loads(save_fact(ctx, id="wrong_team", claim_text="Wrong attribution", data_refs=[first.ref], bindings=[bad]))["ok"]
        assert not json.loads(save_fact(ctx, id="fake", claim_text="Invented support", data_refs=["e99_0.r0"], bindings=[bad | {"ref": "e99_0.r0"}]))["ok"]
        _, missing = execute(registry, ctx, "roster_at_cutoff", roster_key="no such team", season=2026)
        assert missing[0].outcome == "not_found"
        assert not save(ctx, missing[0], "found")["ok"]


def test_actual_population_extreme_and_inherited_incompleteness(v3_ready_snapshot):
    with FrozenLeagueData.open(v3_ready_snapshot) as data:
        registry, ctx = setup(data)
        result, records = execute(registry, ctx, "standings", season=2026)
        teams = [r for r in records if "points_for" in r.fields]
        highest = max(teams, key=lambda r: r.fields["points_for"])
        # Real adapter population passes only explicit matching direction.
        assertion = save(ctx, highest, "points_for", "superlative", superlative_direction="max")
        assert assertion["ok"], (assertion, highest, result.metadata["completeness_warnings"])
        if len({r.fields["points_for"] for r in teams}) > 1:
            assert not save(ctx, highest, "points_for", "superlative", superlative_direction="min")["ok"]
        partial_raw = result.metadata["raw_result"] | {"truncated": True}
        partial = selected_records("partial", "standings", partial_raw, {"season": 2026}, result.metadata["snapshot_seasons"], lambda *_: (None, None))
        ctx.evidence.register("partial", partial)
        selected = next(r for r in partial if "points_for" in r.fields)
        assert not selected.complete
        assert not save(ctx, selected, "points_for", "superlative", superlative_direction="max")["ok"]
        _, limited = execute(registry, ctx, "season_leaders", season=2026, limit=1)
        assert not any(r.complete for r in limited)


def test_actual_trade_direction_and_draft_diagnostics(v3_ready_snapshot, tmp_path):
    changed = _mutated_copy_many(v3_ready_snapshot.artifact.path, tmp_path / "evidence-trade.sqlite", (
        ("UPDATE team_profiles SET team_name='Lebron James' WHERE league_id='league-2026' AND roster_id=1", ()),
        ("UPDATE team_profiles SET team_name='jakb0' WHERE league_id='league-2026' AND roster_id=2", ()),
        ("UPDATE players SET full_name='Kenneth Walker' WHERE player_id='p1'", ()),
        ("UPDATE players SET full_name='DJ Moore' WHERE player_id='p2'", ()),
        ("UPDATE transactions SET type='trade',status='complete' WHERE league_id='league-2026'", ()),
        ("DELETE FROM transaction_moves WHERE league_id='league-2026'", ()),
        ("INSERT INTO transaction_moves(league_id,transaction_id,move_index,roster_id,player_id,asset_type,direction) VALUES ('league-2026','tx1',0,1,'p1','player','drop'),('league-2026','tx1',1,2,'p1','player','add'),('league-2026','tx1',2,1,'p2','player','add'),('league-2026','tx1',3,2,'p2','player','drop')", ()),
        ("INSERT INTO transaction_moves(league_id,transaction_id,move_index,roster_id,asset_type,direction,pick_season,pick_round,pick_original_roster_id) VALUES ('league-2026','tx1',4,1,'pick','pick_in','2026',1,2),('league-2026','tx1',5,2,'pick','pick_out','2026',1,2)", ()),
    ))
    with FrozenLeagueData.open(v3_ready_snapshot.model_copy(update={"artifact": changed})) as data:
        registry, ctx = setup(data)
        result, records = execute(registry, ctx, "team_transactions", roster_key="Lebron James", season=2026, week_from=1, week_to=1)
        kenneth = next(r for r in records if r.subject == "Lebron James" and r.fields.get("player_name") == "Kenneth Walker")
        moore = next(r for r in records if r.subject == "Lebron James" and r.fields.get("player_name") == "DJ Moore")
        capital = next(r for r in records if r.subject == "Lebron James" and "net_draft_picks" in r.fields)
        assert (kenneth.perspective, moore.perspective, capital.fields["net_draft_picks"]) == ("sent", "received", 1)
        assert save(ctx, kenneth, "player_name", "transaction", id="fact_kenneth")["ok"]
        assert save(ctx, moore, "player_name", "transaction", id="fact_moore")["ok"]
        assert save(ctx, capital, "net_draft_picks", "transaction", id="fact_capital")["ok"]
        bad = binding(kenneth, "player_name") | {"perspective": "received"}
        assert not json.loads(save_fact(ctx, id="reversed", claim_text="Trade reversed", data_refs=[kenneth.ref], bindings=[bad], category="transaction"))["ok"]
        draft = "Lebron James received Kenneth Walker and sent DJ Moore. Lebron James spent future flexibility."
        create_artifact(ctx, path="article.md", content=draft)
        checked = json.loads(verify_artifact(ctx, path="article.md", expected_revision=1))
        codes = {d["code"] for d in checked["verification"]["diagnostics"]}
        assert {"trade_direction", "draft_capital_framing"} <= codes
        receipt = ctx.draft_verifications["article.md"]
        edit_artifact(ctx, path="article.md", old_text=draft, new_text="Lebron James sent Kenneth Walker and received DJ Moore plus a first-round pick.", expected_revision=1)
        assert not receipt.is_current(ctx.artifacts.read("article.md"), ctx.brief.brief)
        submitted = json.loads(submit_artifact(ctx, path="article.md", expected_revision=2))
        assert submitted["ok"]
        assert submitted["draft_verification"]["status"] == "DIAGNOSTIC"
        assert not any(d["code"] == "trade_direction" for d in submitted["draft_verification"]["diagnostics"])


def test_runner_real_evidence_records_private_audit_and_completes(ready_snapshot):
    with FrozenLeagueData.open(ready_snapshot) as data:
        registry = ToolRegistry()
        register_datalayer_tools(registry, data)
        register_brief_tools(registry)
        register_artifact_tools(registry)
        recorder = RecordingProbe()
        count = 0

        async def complete(**kwargs):
            nonlocal count
            count += 1
            if count == 1:
                return make_response(tool_calls=[ToolCall("lookup", "standings", {"week": 2})])
            if count == 2:
                visible = json.loads(kwargs["messages"][-1]["content"])
                assert "raw_result" not in visible
                item = next(r for r in visible["records"] if "wins" in r["fields"])
                item = {**visible["scope"], **item}
                selected = {"ref": item["ref"], "field": "wins", "value": item["fields"]["wins"], **{k: item[k] for k in ("subject", "season", "week_from", "week_to", "perspective")}}
                return make_response(tool_calls=[ToolCall("fact", "save_fact", {"id": "fact_wins", "claim_text": "A recorded win total.", "data_refs": [item["ref"]], "bindings": [selected]})])
            if count == 3:
                return make_response(tool_calls=[ToolCall("write", "create_artifact", {"path": "article.md", "content": "# Weekly recap\nThe recorded standings set the scene."})])
            return make_response(tool_calls=[ToolCall("submit", "submit_artifact", {"path": "article.md", "expected_revision": 1})])

        runner = Runner(registry, complete=complete, recorder=recorder)
        output = asyncio.run(runner.run("Write from evidence.", "Weekly recap."))
        assert output.submitted_path == "article.md"
        finish = recorder.finished[0][1]
        assert finish.metadata["raw_result"]["found"] is True
        assert finish.metadata["tool_call_id"] == str(recorder.started[0][0])
        assert finish.result["source"] == "e1_0"
        durable = FinishToolCall(tool_call_id=recorder.started[0][0], status=finish.status,
                                 result=finish.result, result_text=finish.result_text, metadata=finish.metadata)
        assert durable.metadata["raw_result"] == finish.metadata["raw_result"]
        assert runner.tool_context.evidence.resolve("e1_0.r0") is not None


def test_invocation_handles_follow_order_when_completion_reverses():
    registry = ToolRegistry()
    barrier = asyncio.Event()

    async def evidence_handler(ctx, delay):
        source = ctx.evidence_source()
        if delay:
            await barrier.wait()
        else:
            barrier.set()
        ctx.evidence.register(source, (EvidenceRecord(f"{source}.r0", source, "lookup", "found"),))
        return source

    registry.register_context_tool("lookup", evidence_handler, {"type": "function", "function": {"name": "lookup", "parameters": {}}}, "test")
    runner = Runner(registry, complete=lambda **kwargs: None)
    result = asyncio.run(runner._execute_tool_batch([ToolCall("first", "lookup", {"delay": True}), ToolCall("second", "lookup", {"delay": False})], 1))
    assert result == ["e1_0", "e1_1"]
    assert runner.tool_context.current_tool_call_id is None


def test_actual_nested_periods_and_player_metric_owners(ready_snapshot):
    with FrozenLeagueData.open(ready_snapshot) as data:
        registry, ctx = setup(data)
        _, snapshot = execute(registry, ctx, "league_snapshot", week=2)
        _, standings = execute(registry, ctx, "standings", week=2)
        a = next(r for r in snapshot if "wins" in r.fields)
        b = next(r for r in standings if r.subject == a.subject and "wins" in r.fields)
        assert (a.week_from, a.week_to) == (b.week_from, b.week_to) == (1, 2)
        _, players = execute(registry, ctx, "player_weekly_log", player_key="p1")
        points = [r for r in players if "points" in r.fields]
        assert points and all(r.subject == "Player One" for r in points)
        assert all(r.perspective == "Alpha" for r in points)
        _, leaders = execute(registry, ctx, "week_player_leaderboard", week=1)
        assert all(r.subject == r.fields["player_name"] for r in leaders if "points" in r.fields)
        _, roster = execute(registry, ctx, "roster_at_cutoff", roster_key="Alpha")
        assert all(r.season == 2024 and r.week_from == r.week_to == 2 for r in roster)
        assert {r.fields.get("season") for r in roster if "round" in r.fields} >= {"2025", "2026"}
        _, game = execute(registry, ctx, "team_game", roster_key="Alpha", week=1)
        sides = [r for r in game if "points_a" in r.fields or "points_b" in r.fields]
        assert {r.subject for r in sides} == {"Alpha", "Beta"}


@pytest.mark.parametrize("status", ["failed", "pending", None])
def test_actual_uncompleted_transaction_cannot_support_movement(v3_ready_snapshot, tmp_path, status):
    changed = _mutated_copy_many(v3_ready_snapshot.artifact.path, tmp_path / "evidence-uncompleted.sqlite", (
        ("UPDATE transactions SET status=? WHERE league_id='league-2026'", (status,)),
    ))
    with FrozenLeagueData.open(v3_ready_snapshot.model_copy(update={"artifact": changed})) as data:
        registry, ctx = setup(data)
        _, records = execute(registry, ctx, "team_transactions", roster_key="Alpha", season=2026, week_from=1, week_to=1)
        asset = next(r for r in records if "player_name" in r.fields)
        assert asset.outcome == "unavailable"
        assert not save(ctx, asset, "player_name", "transaction")["ok"]


def test_sql_internal_metadata_is_private_and_pages_resolve(ready_snapshot):
    with FrozenLeagueData.open(ready_snapshot) as data:
        registry, ctx = setup(data)
        result, records = execute(registry, ctx, "run_sql", query="SELECT build_key, competition_id, through_week, selected_requests_json FROM snapshot_metadata")
        assert result.metadata["raw_result"]["rows"]
        assert records[0].fields == {"through_week": 2}
        assert "build_key" not in json.dumps(result.result)
        assert not records[0].complete
        page = registry.get_handler("read_evidence")(source=result.result["source"], limit=1)
        assert page.result["records"][0]["ref"] == records[0].ref
        assert registry.get_handler("read_evidence")(source="fabricated").result["found"] is False


def test_unavailable_parent_cannot_be_upgraded_by_partial_child():
    records = selected_records("failed", "standings", {"found": False, "standings": [{"partial": True, "team_name": "Alpha", "wins": 2}]}, {}, [], lambda *_: (None, None))
    assert all(r.outcome == "not_found" for r in records)


def test_actual_renamed_franchise_roster_observations_compare_different_cutoffs(v3_ready_snapshot, tmp_path):
    changed = _changed_franchise_artifact(v3_ready_snapshot, tmp_path)
    populated = _mutated_copy_many(changed.path, tmp_path / "evidence-before-after-rosters.sqlite", (
        ("INSERT INTO roster_players VALUES ('league-2025',7,'p1','starter')", ()),
        ("INSERT INTO roster_players VALUES ('league-2026',1,'p2','starter')", ()),
    ))
    with FrozenLeagueData.open(v3_ready_snapshot.model_copy(update={"artifact": populated})) as data:
        registry, ctx = setup(data)
        _, history = execute(registry, ctx, "franchise_history", franchise_or_primary_roster="Current Guard")
        observations = []
        for appearance in (r for r in history if "roster_lookup" in r.fields):
            _, roster = execute(registry, ctx, "roster_at_cutoff", **appearance.fields["roster_lookup"])
            observations.append(next(r for r in roster if "roster_members" in r.fields))
        before, after = observations
        assert (before.week_to, after.week_to) == (18, 3)
        assert before.subject != after.subject and before.subject_id == after.subject_id
        assert before.fields["roster_members"] != after.fields["roster_members"]
        assert before.temporal_kind == after.temporal_kind == "observation"
        saved = json.loads(save_fact(ctx, id="roster_comparison", claim_text="Listed roster membership differs between the two cutoff observations.", category="comparison", data_refs=[r.ref for r in observations], bindings=[binding(r, "roster_members") for r in observations]))
        assert saved["ok"], saved
        fact = ctx.brief.brief.get_fact("roster_comparison")
        assert any("acquisition timing" in item for item in fact.support_diagnostics)
