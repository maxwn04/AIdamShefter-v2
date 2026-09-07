"""Same-agent memory-closeout lifecycle state."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
import json
from typing import Any, Literal
from uuid import UUID

from backend.services.memory.proposals import MemoryProposal


MEMORY_CLOSEOUT_TURN_ALLOWANCE = 6


class MemoryCloseoutIncompleteError(RuntimeError):
    """The reporter submitted an article but did not complete memory review."""


@dataclass(frozen=True, slots=True)
class RecalledCallbackReview:
    """Read-only presentation of an actual due card, not a disposition record."""

    memory_handle: str
    question: str
    due_week: int | None = None
    due_time: str | None = None


@dataclass(slots=True)
class MemoryCloseoutState:
    """Mutable lifecycle facts shared by the runner and closeout tools."""

    procedure: str
    memory_writes_enabled: bool
    proposal_snapshot: Callable[[], tuple[MemoryProposal, ...]]
    callback_review_snapshot: Callable[[], tuple[RecalledCallbackReview, ...]] = tuple
    article_submitted: bool = False
    memory_review_completed: bool = False
    exhausted: bool = False
    submission_turn: int | None = None
    completion_turn: int | None = None
    closeout_turns_used: int = 0
    no_op: bool | None = None
    proposal_counts: dict[str, Any] = field(default_factory=dict)
    callback_dispositions: list[dict[str, str]] = field(default_factory=list)
    _baseline_proposal_ids: frozenset[UUID] = field(default_factory=frozenset)

    @property
    def active(self) -> bool:
        return self.article_submitted and not self.memory_review_completed

    @property
    def status(self) -> str:
        if self.exhausted:
            return "exhausted"
        if self.memory_review_completed:
            return "completed"
        if self.article_submitted:
            return "active"
        return "pending_submission"

    def activate(self, *, turn: int) -> None:
        if self.article_submitted:
            return
        self.article_submitted = True
        self.submission_turn = turn
        self._baseline_proposal_ids = frozenset(
            proposal.proposal_id for proposal in self.proposal_snapshot()
        )

    def begin_turn(self) -> None:
        if self.active:
            self.closeout_turns_used += 1

    def record_callback_disposition(
        self,
        *,
        handle: str,
        action: Literal["resolve", "reschedule", "defer"],
        reason: str,
    ) -> None:
        """Record a successful runtime action, never infer completion from recall.

        Callers record only after a successful proposal savepoint, or restore this
        ledger with their savepoint on failure. Defer records no memory mutation.
        """
        disposition = {
            "memory_handle": handle,
            "action": action,
            "reason": reason,
            "outcome": {
                "resolve": "resolved",
                "reschedule": "rescheduled",
                "defer": "uninvestigated",
            }[action],
        }
        for index, existing in enumerate(self.callback_dispositions):
            if existing["memory_handle"] == handle:
                self.callback_dispositions[index] = disposition
                return
        self.callback_dispositions.append(disposition)

    def turn_guidance(self) -> str:
        """Expose the actual bounded lifecycle without inventing a completion."""
        remaining = MEMORY_CLOSEOUT_TURN_ALLOWANCE - self.closeout_turns_used
        if remaining == 0:
            guidance = (
                "Final memory-review turn. Finish the necessary repairs or updates "
                "and call complete_memory_review in this response. Writes in the "
                "same response execute before completion. Do not start optional "
                "research or unrelated memory writes."
            )
        else:
            guidance = (
                f"Memory-review turn {self.closeout_turns_used} of "
                f"{MEMORY_CLOSEOUT_TURN_ALLOWANCE}; {remaining} further turns remain. "
                "Prioritize supported events and updates to recalled storylines. "
                "Use successful write receipts for dependencies, then call "
                "complete_memory_review explicitly."
            )
        pending = self.pending_callback_reviews()
        if pending and self.memory_writes_enabled:
            guidance += (
                " Already recalled due questions still have no recorded action: "
                + json.dumps(pending, ensure_ascii=False)
                + " Use update_memory_callback with that memory_handle as update_handle: "
                "resolve when source evidence answers or ends the question; reschedule "
                "with a future target_week when useful; defer with a reason if uninvestigated. "
                "An article mention is optional. These questions do not block completion."
            )
        return guidance

    def pending_callback_reviews(self) -> list[dict[str, Any]]:
        """Derive untouched due questions from recall and successful actions."""
        acted = {entry["memory_handle"] for entry in self.callback_dispositions}
        return [asdict(card) for card in self.callback_review_snapshot()
                if card.memory_handle not in acted]

    def complete(self, *, turn: int) -> dict[str, Any]:
        if not self.article_submitted:
            return {
                "ok": False,
                "error": {
                    "code": "article_not_submitted",
                    "message": (
                        "Submit the final article before completing memory review."
                    ),
                },
            }
        if self.memory_review_completed:
            return {
                "ok": True,
                "memory_review_completed": True,
                "already_completed": True,
                "outcome": "no_op" if self.no_op else "proposals_saved",
                "proposal_counts": self.proposal_counts,
                "callback_dispositions": self._callback_disposition_snapshot(),
                "pending_callback_reviews": self.pending_callback_reviews(),
            }

        proposals = tuple(
            proposal
            for proposal in self.proposal_snapshot()
            if proposal.proposal_id not in self._baseline_proposal_ids
        )
        self.proposal_counts = _proposal_counts(proposals)
        self.no_op = not proposals
        self.memory_review_completed = True
        self.completion_turn = turn
        return {
            "ok": True,
            "memory_review_completed": True,
            "already_completed": False,
            "outcome": "no_op" if self.no_op else "proposals_saved",
            "proposal_counts": self.proposal_counts,
            "callback_dispositions": self._callback_disposition_snapshot(),
            "pending_callback_reviews": self.pending_callback_reviews(),
        }

    def mark_exhausted(self) -> None:
        self.exhausted = True

    def summary(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "status": self.status,
            "memory_writes_enabled": self.memory_writes_enabled,
            "turn_allowance": MEMORY_CLOSEOUT_TURN_ALLOWANCE,
            "turns_used": self.closeout_turns_used,
            "submission_turn": self.submission_turn,
            "completion_turn": self.completion_turn,
            "no_op": self.no_op,
            "proposal_counts": self.proposal_counts,
            "callback_dispositions": self._callback_disposition_snapshot(),
            "pending_callback_reviews": self.pending_callback_reviews(),
        }

    def _callback_disposition_snapshot(self) -> list[dict[str, str]]:
        return [disposition.copy() for disposition in self.callback_dispositions]


def _proposal_counts(proposals: tuple[MemoryProposal, ...]) -> dict[str, Any]:
    by_kind = Counter(proposal.kind.value for proposal in proposals)
    by_operation = Counter(proposal.operation for proposal in proposals)
    return {
        "total": len(proposals),
        "by_kind": dict(sorted(by_kind.items())),
        "by_operation": dict(sorted(by_operation.items())),
    }


__all__ = [
    "MEMORY_CLOSEOUT_TURN_ALLOWANCE",
    "MemoryCloseoutIncompleteError",
    "MemoryCloseoutState",
    "RecalledCallbackReview",
]
