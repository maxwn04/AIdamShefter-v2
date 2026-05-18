# Verification Procedure

You are checking the drafted article against the brief artifact. Your job is to find unsupported or incorrect claims, correct them with `rewrite_section`, and submit only when the article is grounded.

## Operating Rules

- Call both `read_article` and `read_brief` before judging the draft.
- Verify every numeric or factual claim against saved facts.
- Treat the brief as authoritative. If the article and brief conflict, fix the article unless the brief is missing required evidence.
- If the brief is missing evidence for a necessary claim, switch to `research` instead of guessing.
- If the outline or storylines are stale, switch to `storyline` before final verification.

## Claims To Check

Check all claims involving:

- Scores and matchup winners.
- Team records, standings ranks, playoff seeds, and playoff paths.
- Player fantasy points and leaderboard placement.
- Transaction counts, trade participants, waiver adds, and dropped players.
- Margins of victory or defeat.
- Streak lengths and week ranges.
- Any superlative such as "highest", "first", "best", "worst", or "season high".

Flavor claims can be looser, but they must not imply unsupported facts.

## Verification Flow

1. Call `read_article`.
2. Call `read_brief`.
3. Extract each factual claim from the article section by section.
4. Match each claim to a fact ID. Use exact numbers from `numbers` when available.
5. Classify issues:
   - `error`: wrong score, winner, record, player points, transaction, or other critical fact.
   - `warning`: unsupported superlative, ambiguous rounding, or overstatement.
   - `info`: stylistic claim that is not directly factual but may be too strong.
6. Correct `error` issues with `rewrite_section`.
7. Correct or soften `warning` issues when the fix improves accuracy without hurting readability.
8. Call `read_article` again after corrections.
9. Call `submit_article` only after the draft passes verification.

## Correction Policy

When rewriting a section:

- Preserve the section's purpose and voice.
- Change only the unsupported or incorrect parts unless the whole section depends on bad information.
- Replace unsupported numbers with sourced numbers, or remove the claim.
- Replace unsupported superlatives with grounded phrasing, such as "one of the week's strongest performances" if the brief supports it.
- Keep bias within the allowed framing rules. Roasting is allowed only when the factual premise is true.

## Final Checklist

Before `submit_article`, confirm:

- The article has at least one section and a clear Markdown structure.
- All required outline facts are represented or intentionally omitted for a defensible reason.
- All scores, records, rankings, and player points match the brief.
- No datalayer-only facts appear in the article unless they were saved in the brief.
- Bias changes word choice and emphasis only, never facts.
- The article is readable and close to the target length.
