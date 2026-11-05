# Configured roster-slot evidence

The ordinary league overview omitted the roster slots already present in the
frozen source. The reporter could infer a required position from the players a
manager happened to start. For example, two quarterbacks in an observed lineup
do not establish two mandatory quarterback slots.

This candidate exposes the source's `roster_positions` list in that overview and
keeps its exact evidence path. Guidance explains QB, superflex, flex and bench
codes, and explicitly retains the limitation that a retrospective snapshot does
not establish when settings changed. Unknown codes remain visible; missing slots
remain unavailable. It does not reconstruct earlier rules or alter any source
snapshot, score, lineup, memory, verification or article instruction.

Sleeper documents that superflex permits QB, RB, WR or TE in its
[roster-position guide](https://support.sleeper.com/en/articles/4172355-how-can-i-add-additional-roster-positions).
Observed two-quarterback lineups remain legitimate reporting; the candidate does
not treat that wording alone as a false rule claim.

## Validation and experiment

Eighty-six targeted checks pass across frozen query behavior, source-to-evidence
preservation, overview presentation, tool registration and executed evidence.
The baseline had a stale tool-version expectation (5 versus actual 6); the test
now expects this candidate's version 7. Existing golden output stays unchanged;
its compatibility comparison excludes the new additive field, which has direct
source-preservation assertions.

E32 is a preregistered pair of complete first-week runs with the original requests,
empty memory, source pins and Flash settings. Both arms completed submission and
closeout: 29 control calls, 31 treatment calls, $0.190826280 combined conservative
cost. Treatment used superflex in its article and saved league note. Control
inferred a categorical two-quarterback format from observed starters, but did not
explicitly assert a mandatory second quarterback. The preregistered comparative
mandatory-rule criterion therefore remains inconclusive. This supports source
exposure and uptake, not demonstrated overall quality or fewer factual errors.
Tests alone do not establish article-quality or long-term memory improvements.

The operational experiment retains the declared E16/E08 infrastructure ancestry;
this public candidate is separately prepared on current main and does not include
that stack's unmerged preseason classification change. Only import ordering differs
between the operational and public implementation of the new slot exposure.
