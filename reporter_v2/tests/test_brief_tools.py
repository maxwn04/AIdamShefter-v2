"""Tests for runner v2 brief artifact tools."""

import json

from reporter_v2.runner.run_log import RunLog
from reporter_v2.runner.state import ArtifactStore, ProcedureState
from reporter_v2.runner.tools import (
    ToolContext,
    read_brief,
    save_fact,
    save_memory_callback,
    save_storyline,
    set_bias,
    set_outline,
    set_style,
)


def make_ctx() -> ToolContext:
    return ToolContext(
        artifacts=ArtifactStore(),
        procedures=ProcedureState(),
        log=RunLog(),
        turn=3,
    )


def parse_result(result: str) -> dict:
    return json.loads(result)


def test_save_fact_valid():
    ctx = make_ctx()

    result = parse_result(
        save_fact(
            ctx,
            id="fact_001",
            claim_text="Team Taco scored 142.3 points.",
            data_refs=["week_games:week=8"],
            numbers={"points": 142.3},
            category="score",
        )
    )

    assert result == {"ok": True, "fact_id": "fact_001", "brief_revision": 1}
    assert ctx.artifacts.brief.revision == 1
    assert ctx.artifacts.brief.facts[0].id == "fact_001"
    assert ctx.artifacts.brief.facts[0].numbers == {"points": 142.3}
    assert ctx.log.entries[-1].event_type == "artifact_write"
    assert ctx.log.entries[-1].data["key"] == "fact_001"


def test_save_fact_empty_data_refs():
    ctx = make_ctx()

    result = parse_result(
        save_fact(ctx, id="fact_001", claim_text="A claim.", data_refs=[])
    )

    assert result["ok"] is False
    assert "data_refs" in result["error"]
    assert ctx.artifacts.brief.revision == 0
    assert ctx.artifacts.brief.facts == []
    assert ctx.log.entries == []


def test_save_fact_empty_claim():
    ctx = make_ctx()

    result = parse_result(
        save_fact(ctx, id="fact_001", claim_text="  ", data_refs=["source"])
    )

    assert result["ok"] is False
    assert "claim_text" in result["error"]
    assert ctx.artifacts.brief.revision == 0
    assert ctx.artifacts.brief.facts == []


def test_save_fact_upsert():
    ctx = make_ctx()
    save_fact(
        ctx,
        id="fact_001",
        claim_text="Original claim.",
        data_refs=["source:old"],
    )

    result = parse_result(
        save_fact(
            ctx,
            id="fact_001",
            claim_text="Replacement claim.",
            data_refs=["source:new"],
            category="updated",
        )
    )

    assert result["brief_revision"] == 2
    assert len(ctx.artifacts.brief.facts) == 1
    assert ctx.artifacts.brief.facts[0].claim_text == "Replacement claim."
    assert ctx.artifacts.brief.facts[0].data_refs == ["source:new"]
    assert ctx.log.entries[-1].data["operation"] == "update_fact"


def test_save_memory_callback_valid():
    ctx = make_ctx()
    save_fact(
        ctx,
        id="fact_old_trade",
        claim_text="Team A traded Player X before Week 3.",
        data_refs=["transactions:week_to=3"],
        category="transaction",
    )
    save_fact(
        ctx,
        id="fact_current_payoff",
        claim_text="Player X scored 24.1 points against Team A in Week 8.",
        data_refs=["team_game:week=8"],
        category="player",
    )

    result = parse_result(
        save_memory_callback(
            ctx,
            id="callback_trade_regret",
            callback_type="trade_regret",
            claim_text=(
                "Team A's Week 3 trade looked worse after Player X scored 24.1 "
                "points against them in Week 8."
            ),
            old_event_fact_id="fact_old_trade",
            current_event_fact_id="fact_current_payoff",
            why_now="The traded-away player directly hurt his former manager.",
            interestingness_reason="Specific revenge payoff with trade regret.",
            memory_refs=["story_2024_w3_trade"],
            tags=["trade_regret", "week_8"],
        )
    )

    assert result == {
        "ok": True,
        "callback_id": "callback_trade_regret",
        "brief_revision": 3,
    }
    callback = ctx.artifacts.brief.memory_callbacks[0]
    assert callback.old_event_fact_id == "fact_old_trade"
    assert callback.current_event_fact_id == "fact_current_payoff"
    assert callback.memory_refs == ["story_2024_w3_trade"]
    assert ctx.log.entries[-1].data["operation"] == "save_memory_callback"


def test_save_memory_callback_requires_existing_fact_ids():
    ctx = make_ctx()
    save_fact(ctx, id="fact_old_trade", claim_text="A trade happened.", data_refs=["source"])

    result = parse_result(
        save_memory_callback(
            ctx,
            id="callback_trade_regret",
            callback_type="trade_regret",
            claim_text="A callback claim.",
            old_event_fact_id="fact_old_trade",
            current_event_fact_id="missing_current_fact",
            why_now="The current payoff needs proof.",
        )
    )

    assert result["ok"] is False
    assert result["missing_fact_ids"] == ["missing_current_fact"]
    assert ctx.artifacts.brief.memory_callbacks == []


def test_save_memory_callback_upsert():
    ctx = make_ctx()
    save_fact(ctx, id="fact_old", claim_text="Old event.", data_refs=["old"])
    save_fact(ctx, id="fact_current", claim_text="Current event.", data_refs=["current"])
    save_memory_callback(
        ctx,
        id="callback_001",
        callback_type="revenge_game",
        claim_text="Original callback.",
        old_event_fact_id="fact_old",
        current_event_fact_id="fact_current",
        why_now="Original reason.",
    )

    result = parse_result(
        save_memory_callback(
            ctx,
            id="callback_001",
            callback_type="revenge_game",
            claim_text="Updated callback.",
            old_event_fact_id="fact_old",
            current_event_fact_id="fact_current",
            why_now="Updated reason.",
        )
    )

    assert result["brief_revision"] == 4
    assert len(ctx.artifacts.brief.memory_callbacks) == 1
    assert ctx.artifacts.brief.memory_callbacks[0].claim_text == "Updated callback."
    assert ctx.log.entries[-1].data["operation"] == "update_memory_callback"


def test_save_storyline_valid():
    ctx = make_ctx()
    save_fact(ctx, id="fact_001", claim_text="A claim.", data_refs=["source"])

    result = parse_result(
        save_storyline(
            ctx,
            id="story_001",
            headline="Big Swing",
            summary="A major matchup changed the standings.",
            supporting_fact_ids=["fact_001"],
            priority=1,
            tags=["standings"],
        )
    )

    assert result == {"ok": True, "storyline_id": "story_001", "brief_revision": 2}
    assert len(ctx.artifacts.brief.storylines) == 1
    assert ctx.artifacts.brief.storylines[0].revision_at_set == 2
    assert ctx.artifacts.brief.storylines[0].tags == ["standings"]


def test_save_storyline_invalid_fact_ids():
    ctx = make_ctx()

    result = parse_result(
        save_storyline(
            ctx,
            id="story_001",
            headline="Unsupported",
            summary="This has no facts.",
            supporting_fact_ids=["missing_fact"],
        )
    )

    assert result["ok"] is False
    assert result["missing_fact_ids"] == ["missing_fact"]
    assert ctx.artifacts.brief.revision == 0
    assert ctx.artifacts.brief.storylines == []


def test_set_outline():
    ctx = make_ctx()

    result = parse_result(
        set_outline(
            ctx,
            sections=[
                {
                    "title": "Lead",
                    "bullet_points": ["Open with Team Taco."],
                    "required_fact_ids": ["fact_001"],
                    "storyline_ids": ["story_001"],
                }
            ],
        )
    )

    assert result == {"ok": True, "brief_revision": 1}
    assert ctx.artifacts.brief.outline.revision_at_set == 1
    assert ctx.artifacts.brief.outline.sections[0].title == "Lead"
    assert ctx.log.entries[-1].data["operation"] == "set_outline"


def test_set_style_and_bias():
    ctx = make_ctx()

    style_result = parse_result(
        set_style(
            ctx,
            voice="beat reporter",
            pacing="fast",
            humor_level=2,
            formality="sharp casual",
        )
    )
    bias_result = parse_result(
        set_bias(
            ctx,
            favored_teams=["Team Taco"],
            disfavored_teams=["Waiver Wire"],
            intensity=2,
            framing_rules=["Praise decisive wins."],
        )
    )

    assert style_result == {"ok": True, "brief_revision": 1}
    assert bias_result == {"ok": True, "brief_revision": 2}
    assert ctx.artifacts.brief.style.voice == "beat reporter"
    assert ctx.artifacts.brief.bias.favored_teams == ["Team Taco"]


def test_read_brief_staleness():
    ctx = make_ctx()
    set_outline(ctx, sections=[{"title": "Lead"}])
    save_fact(ctx, id="fact_001", claim_text="A later claim.", data_refs=["source"])

    result = parse_result(read_brief(ctx))

    assert result["revision"] == 2
    assert result["staleness_info"] == {
        "outline_stale": True,
        "outline_gap": "1 mutation(s) since outline was set",
    }


def test_read_brief_no_staleness():
    ctx = make_ctx()
    save_fact(ctx, id="fact_001", claim_text="A claim.", data_refs=["source"])
    set_outline(ctx, sections=[{"title": "Lead", "required_fact_ids": ["fact_001"]}])

    result = parse_result(read_brief(ctx))

    assert result["revision"] == 2
    assert result["staleness_info"] == {}
