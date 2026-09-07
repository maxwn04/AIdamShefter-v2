from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

from backend.services.reporter.runner.evidence import EvidenceRecord

from backend.services.reporter.runner.recording import (
    ArtifactMutation,
    ArtifactRecordingError,
)
from backend.services.reporter.runner.research_brief import RESEARCH_BRIEF_PATH
from backend.services.reporter.runner.run_log import RunLog
from backend.services.reporter.runner.state import ArtifactStore, ProcedureState
from backend.services.reporter.runner.tools.brief_tools import (
    BRIEF_TOOL_SPECS,
    read_brief,
    register_brief_tools,
    save_fact,
    save_memory_callback,
    save_storyline,
    set_outline,
)
from backend.services.reporter.runner.tools.context import ToolContext
from backend.services.reporter.runner.tools.registry import ToolRegistry


def _decode(value: str) -> dict[str, object]:
    return json.loads(value)


def _ctx(*, recorder: object | None = None) -> ToolContext:
    return ToolContext(
        artifacts=ArtifactStore(),
        procedures=ProcedureState(),
        log=RunLog(),
        artifact_recorder=recorder,  # type: ignore[arg-type]
    )


def _save_fact(ctx: ToolContext, fact_id: str, claim: str = "Taco won.") -> dict:
    if ctx.evidence.resolve("e1_0.r1") is None:
        ctx.evidence.register("e1_0", (EvidenceRecord(ref="e1_0.r1", source="e1_0", tool="test", outcome="found", fields={"week": 8}),))
    return _decode(
        save_fact(
            ctx,
            id=fact_id,
            claim_text=claim,
            data_refs=["e1_0.r1"],
            bindings=[dict(ref="e1_0.r1", field="week", value=8, subject=None, season=None, week_from=None, week_to=None)],
            numbers={"week": 8},
            category="score",
        )
    )


def test_registers_only_specialized_brief_tools() -> None:
    registry = ToolRegistry()
    register_brief_tools(registry)

    assert registry.tool_names == [
        "save_fact",
        "save_memory_callback",
        "save_storyline",
        "set_outline",
        "read_brief",
    ]
    assert [spec["function"]["name"] for spec in BRIEF_TOOL_SPECS] == (
        registry.tool_names
    )


def test_read_revision_zero_does_not_materialize_projection() -> None:
    ctx = _ctx()

    result = _decode(read_brief(ctx))

    assert result["ok"] is True
    assert result["projection"] is None
    assert result["brief"]["revision"] == 0  # type: ignore[index]
    assert ctx.artifacts.artifacts == {}


def test_first_fact_materializes_projection_and_duplicate_is_noop() -> None:
    ctx = _ctx()

    first = _save_fact(ctx, "fact_taco_win")
    duplicate = _save_fact(ctx, "fact_taco_win")

    assert first["ok"] is True
    assert first["changed"] is True
    assert first["brief_revision"] == 1
    assert duplicate["changed"] is False
    assert duplicate["brief_revision"] == 1
    projection = ctx.artifacts.read(RESEARCH_BRIEF_PATH)
    assert projection.revision == 1
    assert "### fact_taco_win" in projection.content
    writes = [
        entry for entry in ctx.log.entries if entry.event_type == "artifact_write"
    ]
    assert len(writes) == 1
    assert writes[0].data["operation"] == "save_fact"


def test_invalid_fact_returns_structured_error_without_projection() -> None:
    ctx = _ctx()

    result = _decode(
        save_fact(
            ctx,
            id="Fact One",
            claim_text="",
            data_refs=[],
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_brief_input"  # type: ignore[index]
    assert ctx.brief.brief.revision == 0
    assert ctx.artifacts.artifacts == {}


def test_callback_storyline_and_outline_require_existing_references() -> None:
    ctx = _ctx()
    _save_fact(ctx, "fact_old", "A week 3 trade happened.")
    _save_fact(ctx, "fact_current", "The player decided the week 8 rematch.")

    callback = _decode(
        save_memory_callback(
            ctx,
            id="callback_trade_regret",
            callback_type="trade_regret",
            claim_text="The old trade backfired.",
            old_event_fact_id="fact_old",
            current_event_fact_id="fact_current",
            why_now="The player decided the rematch.",
        )
    )
    storyline = _decode(
        save_storyline(
            ctx,
            id="story_trade_regret",
            headline="The trade comes due",
            summary="The old move changed the current matchup.",
            supporting_fact_ids=["fact_old", "fact_current"],
            priority=1,
        )
    )
    outline = _decode(
        set_outline(
            ctx,
            sections=[
                {
                    "title": "Lead",
                    "required_fact_ids": ["fact_current"],
                    "storyline_ids": ["story_trade_regret"],
                }
            ],
        )
    )

    assert callback["ok"] is True
    assert storyline["ok"] is True
    assert outline["ok"] is True
    assert ctx.brief.brief.revision == 5
    assert ctx.artifacts.read(RESEARCH_BRIEF_PATH).revision == 5

    invalid = _decode(
        save_storyline(
            ctx,
            id="story_missing",
            headline="Missing evidence",
            summary="This should fail.",
            supporting_fact_ids=["fact_missing"],
        )
    )
    assert invalid["ok"] is False
    assert invalid["error"]["code"] == "unknown_fact_ids"  # type: ignore[index]
    assert ctx.brief.brief.revision == 5


class _Recorder:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.mutations: list[ArtifactMutation] = []

    def record_artifact_mutation(self, mutation: ArtifactMutation) -> UUID:
        if self.fail:
            raise RuntimeError("database unavailable")
        self.mutations.append(mutation)
        return uuid4()


def test_projection_records_source_brief_tool_call() -> None:
    recorder = _Recorder()
    ctx = _ctx(recorder=recorder)
    execution_id = uuid4()

    with ctx.bind_tool_execution(execution_id):
        result = _save_fact(ctx, "fact_001")

    assert result["ok"] is True
    assert len(recorder.mutations) == 1
    assert recorder.mutations[0].path == RESEARCH_BRIEF_PATH
    assert recorder.mutations[0].source_tool_call_id == execution_id


def test_projection_recording_failure_rolls_back_brief_and_artifact() -> None:
    ctx = _ctx(recorder=_Recorder(fail=True))

    with pytest.raises(ArtifactRecordingError):
        _save_fact(ctx, "fact_001")

    assert ctx.brief.brief.revision == 0
    assert ctx.brief.brief.facts == ()
    assert ctx.artifacts.artifacts == {}


@pytest.mark.parametrize("operation", ["storyline", "outline", "callback"])
def test_dependency_failures_expose_accepted_and_missing_ids_without_mutation(operation: str) -> None:
    recorder = _Recorder()
    ctx = _ctx(recorder=recorder)
    assert _save_fact(ctx, "fact_accepted")["ok"]
    failed_fact = _decode(save_fact(
        ctx, id="fact_missing", claim_text="An unsupported attempted fact.",
        bindings=[{"ref": "e999_0.r0", "field": "wins", "value": 1}],
    ))
    assert not failed_fact["ok"]
    before = ctx.brief.brief.model_dump()
    mutations_before = list(recorder.mutations)
    projection_before = ctx.artifacts.read(RESEARCH_BRIEF_PATH)

    if operation == "storyline":
        result = _decode(save_storyline(
            ctx, id="story_pending", headline="Pending evidence", summary="A dependent story.",
            supporting_fact_ids=["fact_accepted", "fact_missing"],
        ))
    elif operation == "outline":
        result = _decode(set_outline(ctx, sections=[{
            "title": "Lead", "required_fact_ids": ["fact_accepted", "fact_missing"],
            "storyline_ids": ["story_missing"],
        }]))
    else:
        result = _decode(save_memory_callback(
            ctx, id="callback_pending", callback_type="continuity", claim_text="A dependent callback.",
            old_event_fact_id="fact_accepted", current_event_fact_id="fact_missing", why_now="Current payoff.",
        ))

    assert not result["ok"]
    error = result["error"]
    assert error["code"] == "unknown_fact_ids"
    assert error["accepted_fact_ids"] == ["fact_accepted"]
    assert error["missing_fact_ids"] == ["fact_missing"]
    assert error["accepted_storyline_ids"] == []
    assert error["missing_storyline_ids"] == (["story_missing"] if operation == "outline" else [])
    assert error["brief_revision"] == before["revision"]
    assert error["repair"]["action"] == "save_missing_dependencies"
    assert error["repair"]["tools"] == (["save_fact", "save_storyline"] if operation == "outline" else ["save_fact"])
    assert "ok=true" in error["repair"]["instruction"]
    assert ctx.brief.brief.model_dump() == before
    assert ctx.artifacts.read(RESEARCH_BRIEF_PATH) == projection_before
    assert recorder.mutations == mutations_before


def test_outline_reports_missing_storylines_when_facts_are_accepted() -> None:
    ctx = _ctx()
    assert _save_fact(ctx, "fact_accepted")["ok"]
    result = _decode(set_outline(ctx, sections=[{
        "title": "Lead", "required_fact_ids": ["fact_accepted"],
        "storyline_ids": ["story_missing", "story_missing"],
    }]))
    error = result["error"]
    assert error["code"] == "unknown_storyline_ids"
    assert error["accepted_fact_ids"] == ["fact_accepted"]
    assert error["missing_fact_ids"] == []
    assert error["missing_storyline_ids"] == ["story_missing"]
    assert error["repair"]["tools"] == ["save_storyline"]
    assert ctx.brief.brief.revision == 1


def test_dependencies_succeed_after_explicit_successful_saves() -> None:
    ctx = _ctx()
    _save_fact(ctx, "fact_old")
    arguments = dict(id="story_both", headline="Two supported facts", summary="A dependent story.", supporting_fact_ids=["fact_old", "fact_new"])
    assert not _decode(save_storyline(ctx, **arguments))["ok"]
    assert ctx.brief.brief.get_fact("fact_new") is None
    assert ctx.brief.brief.get_storyline("story_both") is None
    assert _save_fact(ctx, "fact_new")["ok"]
    assert _decode(save_storyline(ctx, **arguments))["ok"]
    result = _decode(set_outline(ctx, sections=[{
        "title": "Lead", "required_fact_ids": ["fact_old", "fact_new"],
        "storyline_ids": ["story_both"],
    }]))
    assert result["ok"]
    assert ctx.brief.brief.outline.sections[0].required_fact_ids == ("fact_old", "fact_new")


def test_callback_same_fact_error_gives_precise_repair() -> None:
    ctx = _ctx()
    _save_fact(ctx, "fact_only")
    result = _decode(save_memory_callback(
        ctx, id="callback_same", callback_type="continuity", claim_text="Same fact twice.",
        old_event_fact_id="fact_only", current_event_fact_id="fact_only", why_now="Missing second event.",
    ))
    error = result["error"]
    assert error["code"] == "invalid_callback"
    assert error["accepted_fact_ids"] == ["fact_only"]
    assert error["missing_fact_ids"] == []
    assert error["repair"]["action"] == "choose_distinct_facts"
    assert ctx.brief.brief.revision == 1


def test_unicode_name_repair_is_copyable_and_still_requires_exact_source_value() -> None:
    ctx = _ctx()
    expected = "FANTASY IS LUCK" + "\U0001f92c" * 3
    wrong = "FANTASY IS LUCK" + "\U0001f976" * 3
    ctx.evidence.register("e2_2", (EvidenceRecord(
        ref="e2_2.r40", source="e2_2", tool="transactions", outcome="found",
        fields={"to_team": expected},
    ),))

    def bind(value: str) -> str:
        return save_fact(
            ctx, id="trade_team", claim_text="The recorded receiving team.",
            bindings=[{"ref": "e2_2.r40", "field": "to_team", "value": value}],
        )

    rejected = bind(wrong)
    assert expected in rejected
    assert "\\ud83e" not in rejected
    error = _decode(rejected)["error"]
    assert error["expected_value"] == expected
    assert ctx.brief.brief.get_fact("trade_team") is None
    assert ctx.brief.brief.revision == 0
    assert _decode(bind(error["expected_value"]))["ok"] is True
    assert ctx.brief.brief.get_fact("trade_team").bindings[0].value == expected
