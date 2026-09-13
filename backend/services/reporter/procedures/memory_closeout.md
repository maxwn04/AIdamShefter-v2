# Goal: Preserve Durable Memory After Publication

The article is final and immutable. Review that exact submitted article together with the verified research brief, then preserve only context that is likely to improve future reporting. This is a required closeout step, but it may deliberately produce no memory writes.

## What Is Worth Preserving

- A verified event whose consequences, rivalry, reversal, or later evaluation may matter again.
- An active or dormant storyline with a concise current state and a plausible future payoff.
- A concrete callback condition that should bring an unresolved development back when due.
- Stable team or league context that will remain useful beyond this article.

Do not save article prose, jokes, voice instructions, unsupported inference, generic summaries, or transient details with no likely future narrative value. Memory is continuity state, not an archive of the finished article.

## Reconciliation

Use successful source-bound brief facts as the evidence for new durable claims. The submitted article tells you what was published; its wording is not additional factual proof. Do not propagate a discovered article error into memory. Prior memory supplies the arc's identity and history, not verification of a new result. Brief facts are not copied into durable memory automatically.

Reconcile relevant current cards already in context before writing. Use `search_memory` when the appropriate existing arc is not established and `inspect_memory` for selected detail, history or evidence that clarifies its question. Historical handles stay read-only; select the current card to update it. Do not guess an identity or create a replacement arc because a search returned only an old version.

- Update an existing arc with its `memory_handle` as `update_handle`; use `id` only for a distinct new arc. Preserve its origin, meaningful prior state, subjects and evidence. Summarize the development from the prior state to the supported current state instead of replacing history with this week's recap.
- Add newly relevant subjects with stable team selectors and the default merge behavior. Omit unchanged optional fields; provide the required headline and current summary. Use subject replacement only for an intentional relationship correction, never to get past a name-resolution error. Preserve all intended subjects when repairing a rejected selector.
- Save supporting events first and wait for successful receipts, then update each selected storyline once with all relevant new event IDs. Check that event headline and summary agree with the source-derived identities and every asset direction, including pick ownership. Structured event validation does not certify authored prose.
- Let the arc's actual question determine its status. A new phase can continue the same arc. If separate arcs overlap, assess how the current outcome bears on each selected arc: a title result may settle more than one prior uncertainty. Keep their summaries mutually coherent without automatically closing unrelated arcs or callbacks. Do not leave a known answered question presented as unknown merely because its payoff was saved elsewhere.
- Preserve an earlier error as history while making a source-supported correction explicit in the current summary; never present an unverified older narrative as an established historical fact. Quiet arcs can remain unchanged, and a no-op is preferable to a cosmetic weekly rewrite.

If memory writes are disabled, do not retry blocked writes or invent substitute bookkeeping. Complete the review as an intentional no-op.

## Callback Updates

Use `update_memory_callback` with the selected callback's `memory_handle` as `update_handle` and a concise, accurate reason. Read the actual question and its originating event or arc before choosing an action. Inspect linked evidence when a short label leaves the player, transaction or prior state ambiguous.

- Resolve only when the evidence answers that question. State the supported answer and why the evidence bears on it. For a question with several required parts, answering standings alone does not answer an acquisition-impact part; a true alternative can answer an explicitly either/or condition. Contradiction can settle a hypothesis when the correct identity and time window are established.
- Unknown, unavailable or uninvestigated is not an answered outcome. A due date, article mention, season ending or parent resolution alone is not evidence for resolution. Do not substitute another player's move, a later transaction or general team success for the questioned event's effect.
- Reschedule with a future `target_week` when an unanswered question has a useful later review point. Preserve the original question rather than silently narrowing it to the part already answered. Defer a question you did not investigate; this records an uninvestigated disposition without changing canonical state or its date. An investigated but unanswered question may remain unchanged when no useful future date is established.

Successful updates record their own disposition. Do not reconstruct a separate completion receipt. An article mention is optional. Resolving a storyline does not resolve its callbacks, and callbacks you did not inspect remain unchanged. Reuse or reschedule an existing matching question instead of accumulating duplicate triggers. Review useful callbacks within the available closeout turns; accounting for every due callback is not a completion requirement.

## Required Finish

When useful durable items have been saved—or when you have determined that none are warranted—call `complete_memory_review`. Do not return a normal assistant message and do not attempt to revise the submitted article.
