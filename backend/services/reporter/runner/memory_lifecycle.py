"""Pre-run memory hook for a reporter article run.

Structured post-run brief persistence intentionally does not live here: the
reporter's brief is now an unparsed Markdown artifact. Durable artifact and
execution recording belongs to the later reporting-manager slice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reporter_memory.context_store import ContextStore


def prepare_memory_run(
    context_store: ContextStore | None,
    *,
    week: int,
    allow_writes: bool,
) -> None:
    """Mark week-scoped memory stale before a writable run."""
    if context_store is not None and allow_writes:
        context_store.mark_stale(week)
