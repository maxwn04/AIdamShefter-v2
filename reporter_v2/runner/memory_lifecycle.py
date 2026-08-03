"""Pre/post memory hooks for a reporter v2 article run.

Owns mark_stale before the agent loop and persist-on-submit afterward.
Tool registration stays in the article generator; this module only handles
run lifecycle around an existing ContextStore.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from reporter_v2.runner.schemas import ArticleOutput, ReportBrief

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


def persist_brief_facts(
    context_store: ContextStore,
    brief: ReportBrief,
    *,
    week: int,
) -> None:
    """Persist verified brief facts under their final brief storylines."""
    for storyline in brief.storylines:
        facts = [brief.get_fact(fact_id) for fact_id in storyline.supporting_fact_ids]
        payload = [
            {
                "id": fact.id,
                "claim_text": fact.claim_text,
                "data_refs": fact.data_refs,
                "numbers": fact.numbers,
                "category": fact.category,
            }
            for fact in facts
            if fact is not None
        ]
        if payload:
            context_store.persist_facts(payload, storyline.id, week=week)


def finalize_memory_run(
    context_store: ContextStore | None,
    output: ArticleOutput,
    *,
    week: int,
    allow_writes: bool,
) -> None:
    """Persist brief facts after a successful submit when writes are allowed."""
    if (
        allow_writes
        and context_store is not None
        and output.run_log_summary.get("submitted") is True
    ):
        persist_brief_facts(context_store, output.brief, week=week)
