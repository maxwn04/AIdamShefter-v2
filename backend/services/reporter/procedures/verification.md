# Verification Procedure

Use this procedure for a detailed claim-level audit of the chosen publishable draft against the structured brief. Verification is usually the last activity before submission, but it is not a one-way terminal phase: follow important gaps into targeted research, storyline repair, or redrafting, then resume the audit.

## Operating Rules

- Use `list_artifacts` only when the draft path is unknown. Read the draft or call `read_brief` only when you do not already hold its current state.
- Honor readiness warnings. Do not rely on stale callbacks, storylines, or outline references until they are refreshed against current fact revisions.
- Verify every numeric or factual claim against saved facts.
- Treat the brief as authoritative. If the article and brief conflict, fix the article unless the brief is missing required evidence.
- If the brief is missing evidence for a necessary claim, investigate the narrow gap directly and save the result with `save_fact`. Load `research` only when the problem requires substantial exploration.
- If verification exposes a weak or unsupported framing choice, revise it directly. Load `storyline` only when the article needs broader narrative restructuring.
- Treat callback claims as factual claims. They need evidence for both the older event and the current event.
- Before submission, perform a deliberate memory harvest when proposal tools are available. Review the final lead storylines, verified callbacks, meaningful transactions, reversals, playoff stakes, and future rematch or evaluation conditions. Buffer only items with plausible future callback value or season-long significance; routine results do not need to persist.

## Claims To Check

Check all claims involving:

- Scores and matchup winners.
- Team records, standings ranks, playoff seeds, and playoff paths.
- Player fantasy points and leaderboard placement.
- Transaction counts, trade participants, waiver adds, and dropped players.
- Margins of victory or defeat.
- Streak lengths and week ranges.
- Any superlative such as "highest", "first", "best", "worst", or "season high".
- Any callback, revenge, regret, reversal, payoff, rematch, rivalry, or "full circle" claim.

Flavor claims can be looser, but they must not imply unsupported facts.

## Callback Checks

For every callback paragraph:

- Map the older event to a saved fact ID whose claim was re-verified against frozen data.
- Map the current payoff to a current-run saved fact ID.
- Confirm both sides of every verified callback exist in the brief.
- Confirm the paragraph explains what happened then, what happened now, and why the meaning changed.
- Treat unsourced narrative memory as research context only, not prose support.
- Reject or soften callbacks where the older event is real but the current payoff is weak, incidental, or not proven.

## Verification Flow

1. Establish the current draft path, content, and revision, and the current structured brief state. Reuse state returned by recent operations when available.
2. Extract each factual claim from the article section by section.
3. Match each claim to a fact ID and use the exact saved numbers.
4. Classify issues:
   - `error`: wrong score, winner, record, player points, transaction, or other critical fact.
   - `warning`: unsupported superlative, ambiguous rounding, or overstatement.
   - `info`: stylistic claim that is not directly factual but may be too strong.
5. Correct `error` issues with exact, single-match `edit_artifact` calls.
6. Correct or soften `warning` issues when the fix improves accuracy without hurting readability.
7. When a correction requires new evidence or reframing, resolve it and continue the audit from the affected section; do not restart the entire workflow.
8. After each edit, use its returned content and revision for the next check. Perform one final whole-article review after substantive corrections.
9. Call `submit_artifact(path=<draft_path>, expected_revision=<current>)` only after the draft passes verification.

## Correction Policy

When editing the article:

- Preserve the passage's purpose and voice.
- Change only the unsupported or incorrect parts unless the whole section depends on bad information.
- Replace unsupported numbers with sourced numbers, or remove the claim.
- Replace unsupported superlatives with grounded phrasing, such as "one of the week's strongest performances" if the brief supports it.
- Keep bias within the allowed framing rules. Roasting is allowed only when the factual premise is true.
- If a target occurs zero or multiple times, read the current article and choose a more precise exact replacement rather than guessing.

## Final Checklist

Before `submit_artifact`, confirm:

- The article is non-empty and has a clear Markdown structure.
- All required outline facts are represented or intentionally omitted for a defensible reason.
- All scores, records, rankings, and player points match the brief.
- No datalayer-only facts appear in the article unless they were saved in the brief.
- Bias changes word choice and emphasis only, never facts.
- The article is readable and close to the target length.

Submission pins the current chosen draft snapshot and ends the reporter loop. A revision conflict requires another read and verification pass.
