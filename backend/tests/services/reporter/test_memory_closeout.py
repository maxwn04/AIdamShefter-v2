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
        "pending_callback_reviews": [],
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


def test_actual_due_question_reappears_at_closeout_without_becoming_a_gate() -> None:
    from backend.services.reporter.runner.memory_closeout import RecalledCallbackReview

    due = RecalledCallbackReview(memory_handle="memory_1",
        question="Have GIBBS or iAmWeird sustained their early scoring edge?", due_week=3)
    state = MemoryCloseoutState(procedure="# Closeout", memory_writes_enabled=True,
        proposal_snapshot=lambda: (), callback_review_snapshot=lambda: (due,))
    state.activate(turn=15)
    state.begin_turn()
    guidance = state.turn_guidance()
    assert "memory_1" in guidance and due.question in guidance and '"due_week": 3' in guidance
    assert "update_memory_callback" in guidance and "defer" in guidance and "reschedule" in guidance
    result = state.complete(turn=16)
    assert result["ok"] is True
    assert result["callback_dispositions"] == []
    assert result["pending_callback_reviews"][0]["memory_handle"] == "memory_1"
    assert result["proposal_counts"]["total"] == 0


def test_pending_context_uses_only_successful_dispositions_and_is_read_only() -> None:
    from backend.services.reporter.runner.memory_closeout import RecalledCallbackReview

    cards = tuple(RecalledCallbackReview(memory_handle=f"memory_{number}", question=f"Question {number}", due_week=3)
                  for number in (1, 2, 3, 4))
    state = MemoryCloseoutState(procedure="# Closeout", memory_writes_enabled=True,
        proposal_snapshot=lambda: (), callback_review_snapshot=lambda: cards)
    state.activate(turn=15)
    for number, action in ((1, "resolve"), (2, "reschedule"), (3, "defer")):
        state.record_callback_disposition(handle=f"memory_{number}", action=action, reason="Deliberate action")
    pending = state.pending_callback_reviews()
    assert [card["memory_handle"] for card in pending] == ["memory_4"]
    pending[0]["question"] = "Changed copy"
    assert state.pending_callback_reviews()[0]["question"] == "Question 4"
    assert "Question 1" not in state.turn_guidance()
    assert "Question 4" in state.turn_guidance()
    assert state.complete(turn=16)["ok"] is True
    assert cards[3].question == "Question 4"


def test_read_only_closeout_does_not_suggest_blocked_callback_writes() -> None:
    from backend.services.reporter.runner.memory_closeout import RecalledCallbackReview

    state = MemoryCloseoutState(procedure="# Closeout", memory_writes_enabled=False,
        proposal_snapshot=lambda: (), callback_review_snapshot=lambda: (
            RecalledCallbackReview(memory_handle="memory_1", question="Still open", due_week=3),))
    state.activate(turn=1)
    assert "update_memory_callback" not in state.turn_guidance()
    assert state.complete(turn=2)["pending_callback_reviews"][0]["question"] == "Still open"


def test_closeout_snapshot_contains_only_actual_writable_due_cards() -> None:
    from uuid import UUID
    from backend.services.memory import GenerationMemoryContext
    from backend.services.reporter.config import ReportConfig, TimeRange
    from backend.services.reporter.runner.tools.memory_tools import TypedMemoryAdapter
    from backend.tests.services.reporter.test_memory_recall import (
        COMPETITION_ID, SEASON_ID, REVISION_ID, CUTOFF, FrozenData, Retrieval, _trigger,
    )

    due = _trigger(10, target_week=3)
    historical = _trigger(11, target_week=3).model_copy(update={"current_at_pin": False})
    future = _trigger(12, target_week=16)
    retrieval = Retrieval(triggers=(due, historical, future))
    memory = GenerationMemoryContext(competition_id=COMPETITION_ID, generation_id=UUID(int=99),
        pinned_revision_id=REVISION_ID, retrieval=retrieval, competition_season_id=SEASON_ID,
        week=15, knowledge_cutoff_at=CUTOFF)
    adapter = TypedMemoryAdapter(memory, FrozenData())
    assert adapter.callback_review_snapshot() == ()
    plan = adapter.build_recall(ReportConfig(time_range=TimeRange.single_week(15)))
    cards = adapter.callback_review_snapshot()
    assert len(cards) == 1
    assert cards[0].memory_handle in {card["memory_handle"] for card in plan.result["due_callbacks"]}
    assert adapter._presentation.resolve_handle(cards[0].memory_handle).version.version_id == due.memory.version.version_id
    assert cards[0].due_week == 3
    assert memory.proposal_snapshot() == ()
