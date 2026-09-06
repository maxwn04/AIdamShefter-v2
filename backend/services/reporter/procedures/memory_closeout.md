# Goal: Preserve Durable Memory After Publication

The article is final and immutable. Review that exact submitted article together with the verified research brief, then preserve only context that is likely to improve future reporting. This is a required closeout step, but it may deliberately produce no memory writes.

## What Is Worth Preserving

- A verified event whose consequences, rivalry, reversal, or later evaluation may matter again.
- An active or dormant storyline with a concise current state and a plausible future payoff.
- A concrete callback condition that should bring an unresolved development back when due.
- Stable team or league context that will remain useful beyond this article.

Do not save article prose, jokes, voice instructions, unsupported inference, generic summaries, or transient details with no likely future narrative value. Memory is continuity state, not an archive of the finished article.

## Reconciliation

Use the finalized article and verified brief as your evidence boundary. Brief facts are working evidence and are not copied into durable memory. When an existing remembered arc may overlap, use `search_memory` to reconcile it before writing. Do not guess hidden identities or treat remembered material as proof. Use the existing semantic memory tools to create or update the appropriate event, storyline, trigger, team context, or league note.

If memory writes are disabled, do not retry blocked writes or invent substitute bookkeeping. Complete the review as an intentional no-op.

## Callback Updates

Use `update_memory_callback` with the recalled callback's `update_handle` and a concise reason. Resolve a question when the available evidence supports an answer or a deliberate end to that question. Reschedule an open question with a future `target_week` when a later review will be useful. Defer a question you did not investigate; it stays open and its existing review date is unchanged.

Successful updates record their own disposition. Do not reconstruct a separate completion receipt. An article mention is optional. Resolving a storyline does not resolve its callbacks, and callbacks you did not inspect remain unchanged. Review useful callbacks within the available closeout turns; accounting for every due callback is not a completion requirement.

## Required Finish

When useful durable items have been saved—or when you have determined that none are warranted—call `complete_memory_review`. Do not return a normal assistant message and do not attempt to revise the submitted article.
