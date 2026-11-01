# Original context for storyline review leads

A storyline's current summary can replace the question that originally justified
keeping it. Asking the reporter to preserve that question is less useful when
only the current summary is presented. The original remains in immutable history,
but obtaining it requires an explicit inspection that the completed baseline did
not use in any of its 17 articles.

This candidate adds bounded first-version context alongside each updated card in
the existing automatic storyline review pool. It changes no selection/ranking,
card limit, current update handle, source cutoff, writing prompt or resolution
rule. First-version cards do not repeat their own context. The pool still contains
at most three leads and retains its existing exclusions for explicit focus and
storylines already delivered by due callbacks. Other recall groups are unchanged.

The original context includes its headline, summary, callback question, season
and week where available. It is labeled historical narrative, not verified current
facts or compulsory article coverage. It has no update selector. The current lead
is still the editable card, and its history can be inspected for the full text.
Hidden metadata binds the added projection to the exact original version.

The implementation reuses pinned history inspection and its introduction-week
and season boundaries. It accepts only version one of the same item; missing or
filtered/gapped history is omitted rather than replaced by a later version.
Headlines are bounded to 200 characters, summaries to 2,000 and callback questions
to 400; clipping is explicit. The largest original summary in the baseline was
1,016 characters, so this bound retains all recorded original questions. This
adds context and up to three bounded history reads; it does not make old narrative
claims true or guarantee the model will respect them.

For example, an original question might ask whether an acquisition improves the
weekly scoring floor, while the current summary asks whether the team holds its
seed. Showing both makes that change visible. It does not require the team to stay
in one story forever or prevent a supported closure and a separate new question.

Forty targeted tests passed on the operational candidate and the clean main-based
candidate. PostgreSQL regressions cover exact original/current separation,
unchanged old-pin output after a later commit, introduction-week filtering,
no fallback when the original is unavailable, explicit clipping and retention of
the current update target. A legacy unit fixture was extended with the history
inspection interface; no provider call is part of these tests.

The live comparison is preregistered, with one baseline and one treatment Week 7
from the identical original post-Week 6 checkpoint. The runtime parent is the
completed E06 season, including the E04 question-identity paragraph and source-
identity fix. Only this presentation file differs. The independently scoped PR
is based on main and includes neither of those other candidates nor the rejected
E05 rule or inconclusive E07 paragraph.

The selected-week gate assesses feasibility, temporal/current-handle correctness,
article/closeout completion and major grounding regressions. It separately records
question retention, replacement, legitimate closure, ambiguous scope and no-update
outcomes. A qualitative tie is not a superiority result. A safe gate may justify a
separately preregistered empty-memory season to assess long-run lifecycle behavior;
no lifecycle or article-quality improvement is claimed from the offline tests.

The selected-week gate completed both arms: 34 control calls and 31 treatment
calls, with four and five closeout calls respectively. All three origin bindings
were exact. First-request messages matched after removing only the added origin
context; tools/current selections matched, all 69 inherited versions and contents
were unchanged, and no duplicate source identities or broken evidence links
appeared. Aggregate gate cost was $0.27468, with no new uncertain request.

Behavior remains mixed. The treatment still narrowed a roster-risk question toward
seeding and overstated what one acquisition return answered while leaving the card
active. It also moved an older scoring lead into the wrong historical week. The
same old fact was already present in current context, so attribution to the added
origin is unresolved. The control article had a separate prior-record error.
Exact binding does not certify historical prose or improve question adherence by
itself. More memory writes and fewer calls are not general quality evidence.

A separately preregistered 17-week season is running from empty memory to measure
all-arc lifecycle behavior, origin exposure, stale-history errors and acquisition
callbacks. The gate is technical feasibility evidence, not an efficacy promotion.
This remains an exploratory draft pending the longitudinal audit.

Private articles, source identifiers, raw traces and account records remain
outside this repository. See the consolidated experiment ledger in draft PR #261
for the preceding experiments and their limitations.
