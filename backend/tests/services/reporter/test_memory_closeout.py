from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from backend.services.reporter.runner.memory_closeout import MemoryCloseoutState
from backend.services.reporter.runner.run_log import RunLog
from backend.services.reporter.runner.state import ArtifactStore, ProcedureState
from backend.services.reporter.runner.tools.context import ToolContext
from backend.services.reporter.runner.tools.memory_closeout_tools import (
    MEMORY_CLOSEOUT_TOOL_SPECS,
    complete_memory_review,
)


def _context(
    state: MemoryCloseoutState | None,
) -> ToolContext:
    return ToolContext(
        artifacts=ArtifactStore(),
        procedures=ProcedureState(),
        log=RunLog(),
        turn=4,
        memory_closeout=state,
    )


def test_completion_tool_has_empty_model_bookkeeping_schema() -> None:
    spec = MEMORY_CLOSEOUT_TOOL_SPECS[0]["function"]

    assert spec["name"] == "complete_memory_review"
    assert spec["parameters"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def test_completion_requires_submission_and_unavailable_runs_are_bounded() -> None:
    state = MemoryCloseoutState(
        procedure="# Closeout",
        memory_writes_enabled=True,
        proposal_snapshot=lambda: (),
    )

    early = complete_memory_review(_context(state))
    unavailable = complete_memory_review(_context(None))

    assert early == {
        "ok": False,
        "error": {
            "code": "article_not_submitted",
            "message": "Submit the final article before completing memory review.",
        },
    }
    assert unavailable["error"]["code"] == "memory_closeout_unavailable"


def test_completion_derives_delta_counts_and_is_idempotent() -> None:
    proposals = [
        SimpleNamespace(
            proposal_id=uuid4(),
            kind=SimpleNamespace(value="fact"),
            operation="create",
        )
    ]
    state = MemoryCloseoutState(
        procedure="# Closeout",
        memory_writes_enabled=True,
        proposal_snapshot=lambda: tuple(proposals),  # type: ignore[arg-type]
    )
    state.activate(turn=3)
    proposals.extend(
        [
            SimpleNamespace(
                proposal_id=uuid4(),
                kind=SimpleNamespace(value="storyline"),
                operation="create",
            ),
            SimpleNamespace(
                proposal_id=uuid4(),
                kind=SimpleNamespace(value="storyline"),
                operation="replace",
            ),
        ]
    )
    ctx = _context(state)

    completed = complete_memory_review(ctx)
    repeated = complete_memory_review(ctx)

    expected_counts = {
        "total": 2,
        "by_kind": {"storyline": 2},
        "by_operation": {"create": 1, "replace": 1},
    }
    assert completed == {
        "ok": True,
        "memory_review_completed": True,
        "already_completed": False,
        "outcome": "proposals_saved",
        "proposal_counts": expected_counts,
        "callback_dispositions": [],
    }
    assert repeated == {
        **completed,
        "already_completed": True,
    }
    events = [entry.data["event"] for entry in ctx.log.entries]
    assert events == ["memory_review_completed"]


def test_completion_records_explicit_noop_for_write_disabled_run() -> None:
    state = MemoryCloseoutState(
        procedure="# Closeout",
        memory_writes_enabled=False,
        proposal_snapshot=lambda: (),
    )
    state.activate(turn=2)
    ctx = _context(state)

    result = complete_memory_review(ctx)

    assert result["outcome"] == "no_op"
    assert result["proposal_counts"] == {
        "total": 0,
        "by_kind": {},
        "by_operation": {},
    }
    assert [entry.data for entry in ctx.log.entries] == [
        {
            "event": "memory_review_completed",
            "outcome": "no_op",
            "proposal_counts": result["proposal_counts"],
            "callback_dispositions": [],
        },
        {
            "event": "memory_review_noop",
            "memory_writes_enabled": False,
        },
    ]


def test_callback_dispositions_report_successful_actions_without_duplicate_receipts() -> None:
    state = MemoryCloseoutState(
        procedure="# Closeout",
        memory_writes_enabled=True,
        proposal_snapshot=lambda: (),
    )
    state.activate(turn=2)
    state.record_callback_disposition(
        handle="memory_1", action="resolve", reason="The final result answers the question."
    )
    state.record_callback_disposition(
        handle="memory_2", action="reschedule", reason="Review after the next matchup."
    )
    state.record_callback_disposition(
        handle="memory_3", action="defer", reason="The trade contribution was not investigated."
    )
    state.record_callback_disposition(
        handle="memory_1", action="resolve", reason="The final result answers the question."
    )

    ctx = _context(state)
    result = complete_memory_review(ctx)

    assert [entry["outcome"] for entry in result["callback_dispositions"]] == [
        "resolved", "rescheduled", "uninvestigated"
    ]
    assert state.summary()["callback_dispositions"] == result["callback_dispositions"]
    assert ctx.log.entries[0].data["callback_dispositions"] == result["callback_dispositions"]
    assert complete_memory_review(ctx)["callback_dispositions"] == result["callback_dispositions"]
    result["callback_dispositions"][0]["reason"] = "Changed receipt"
    assert state.callback_dispositions[0]["reason"] == "The final result answers the question."


def test_defer_does_not_create_a_proposal_or_require_other_callback_dispositions() -> None:
    state = MemoryCloseoutState(
        procedure="# Closeout",
        memory_writes_enabled=True,
        proposal_snapshot=lambda: (),
    )
    state.activate(turn=2)
    state.record_callback_disposition(
        handle="memory_1", action="defer", reason="Not investigated."
    )
    for _ in range(6):
        state.begin_turn()

    result = complete_memory_review(_context(state))

    assert result["ok"] is True and result["outcome"] == "no_op"
    assert result["proposal_counts"]["total"] == 0
    assert result["callback_dispositions"] == [{
        "memory_handle": "memory_1",
        "action": "defer",
        "reason": "Not investigated.",
        "outcome": "uninvestigated",
    }]
    assert state.summary()["turn_allowance"] == 6
