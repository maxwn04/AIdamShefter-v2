from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

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
    return _decode(
        save_fact(
            ctx,
            id=fact_id,
            claim_text=claim,
            data_refs=["league_snapshot:week=8"],
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
