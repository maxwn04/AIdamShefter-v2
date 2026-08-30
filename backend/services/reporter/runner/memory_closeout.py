"""Same-agent memory-closeout lifecycle state."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from backend.services.memory.proposals import MemoryProposal


MEMORY_CLOSEOUT_TURN_ALLOWANCE = 6


class MemoryCloseoutIncompleteError(RuntimeError):
    """The reporter submitted an article but did not complete memory review."""


@dataclass(slots=True)
class MemoryCloseoutState:
    """Mutable lifecycle facts shared by the runner and closeout tools."""

    procedure: str
    memory_writes_enabled: bool
    proposal_snapshot: Callable[[], tuple[MemoryProposal, ...]]
    article_submitted: bool = False
    memory_review_completed: bool = False
    exhausted: bool = False
    submission_turn: int | None = None
    completion_turn: int | None = None
    closeout_turns_used: int = 0
    no_op: bool | None = None
    proposal_counts: dict[str, Any] = field(default_factory=dict)
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
        }


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
]
