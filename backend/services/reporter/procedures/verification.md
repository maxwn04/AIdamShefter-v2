# Goal: Earn Publication Confidence

Use this guide when a publishable draft exists and the remaining question is whether its facts, framing, coverage, and current revision are trustworthy enough to submit. Verification may uncover a reason to research, reshape, or redraft before returning to this goal.

## Success Looks Like

- Every material factual claim in the article maps to an accurate saved fact.
- Scores, winners, records, ranks, player totals, transactions, margins, streaks, week ranges, playoff claims, and superlatives are correct and sufficiently supported.
- Callbacks contain reverified evidence for both the older event and current payoff.
- Historical comparisons, records, and superlatives have saved evidence for every season involved, including explicit season arguments on season-scoped calls.
- Suspicious or conflicting evidence has been independently checked rather than copied from the brief by default.
- The article's framing is proportional to its evidence, matches the request, and does not imply unsupported causality or certainty.
- The selected artifact is readable, coherent, close to the requested length, and at the current known revision.

## Tool Choices

- Use `list_artifacts` only when the publishable path is unknown.
- Reuse the current draft and brief state when available. Use `read_artifact` or `read_brief` when state is unknown or a complete review will add value.
- Use the smallest targeted datalayer view to resolve a missing, suspicious, or conflicting claim, then save the corrected evidence.
- Use `edit_artifact` for a real correction or meaningful improvement, carrying forward the returned revision.
- Use `verify_artifact` with the actual draft path and revision. Its bounded checks tie a receipt to the article hash/revision and brief revision. Edits to either invalidate the receipt. Review its DIAGNOSTIC findings against the source; they are advisory pattern matches, not proof of prose entailment. Submission refreshes stale checks and rejects unresolved evidence references.
- Use `submit_artifact` only after the actual draft meets the publication goal. Submission pins that revision. When its result supplies the mandatory `memory_closeout` procedure, the same conversation continues for memory review and ends only through `complete_memory_review`.

## Audit Judgment

- Check the article itself, not merely whether the workflow produced facts, storylines, or an outline.
- Check each trade asset from the named team's perspective: sent stays sent and received stays received. A net gain in draft-pick count cannot alone justify “spent future flexibility”; count also does not prove value. Confirm that a quoted record belongs to the named team and stated period.
- Generic bindings prove selected field traceability only. Superlatives need a complete supported population and the claimed min/max direction; sole-record wording also requires uniqueness. A standings lead or memory of a title cannot establish a championship: select the actual winners-bracket championship outcome. Narrow claims when comparison populations or historical windows are unavailable.
- Retain meaningful caveats in the draft itself. A hidden diagnostic about failed historical roster recovery does not disclose that limitation to readers. Do not copy private source payloads, durable IDs, or audit receipts into prose.
- Treat the brief as structured evidence, not infallible truth. Confirm that source references match calls actually made and that saved claims faithfully represent their results.
- Pay special attention to high-impact numbers, names, winners, transactions, comparative claims, and words such as “highest,” “first,” “best,” “worst,” or “season high.”
- A flavor claim may be interpretive, but it must not smuggle in an unsupported factual premise.
- For callbacks, confirm what happened then, what happened now, and why the meaning changed. Reject or soften a connection whose current payoff is weak or incidental.
- Confirm that historical team identity came from `franchise_history` or a durable franchise UUID, never an independent match on an old team or manager name.
- Honor stale-dependency warnings. Refresh or remove stale callbacks, storylines, and outline references before relying on them.
- Correct the smallest passage that resolves an issue unless the surrounding section depends on the same bad premise.
- Replace unsupported specificity with verified specificity or appropriately qualified language.
- Preserve voice while correcting facts. Bias never excuses an inaccurate premise.
- If the draft is already correct, do not perform a no-op edit merely to demonstrate verification.

## Stop Or Switch

Return to research when missing or questionable evidence could change a material claim. Return to storyline work when the facts are sound but the thesis or emphasis is misleading. Return to drafting when corrections require substantial prose changes.

This goal is complete when no known material issue remains and another review would mostly repeat the same checks. Submit the current verified revision directly; a revision conflict means the artifact must be reread and publication confidence re-established. After a successful submission, do not revise the article. Follow any mandatory closeout procedure returned by the tool.
