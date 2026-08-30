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
        },
        {
            "event": "memory_review_noop",
            "memory_writes_enabled": False,
        },
    ]
