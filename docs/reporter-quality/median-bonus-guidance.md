# Median bonus terminology and matched gate

The reporter currently receives guidance calling Sleeper's additional standings
decision a “league-average bonus matchup.” That wording can invite an arithmetic
mean interpretation even though the documented feature uses the weekly median.

This candidate changes only that guidance. It names the median, explains a tie at
the median and the regular-season scope, and preserves the existing distinction
between standings decisions and head-to-head game outcomes. Raw API keys,
normalized fields, frozen snapshots, record arithmetic, memory, prompts and the
verifier remain unchanged. In particular, records still come from the provider's
recorded results; this patch does not recompute standings.

## Evidence and limits

[Sleeper's feature documentation](https://support.sleeper.com/en/articles/3971690-extra-game-each-week-against-league-median)
describes a second regular-season result against the weekly median, a tie when
equal, and no such result for playoff or consolation games. The page displayed an
update date of September 15, 2026 when inspected on November 1, 2026. It is not a
dated specification for the historical season being replayed.

The frozen league setting enables `league_average_match`. An offline audit of
168 regular-season team-weeks matched all recorded decisions with the median;
using the arithmetic mean disagreed on 12. The public API reference does not
document the meaning of that raw key. Connecting the legacy key to the documented
feature is therefore an inference supported by the enabled setting, recorded
extra decisions and the complete reconstruction, rather than the name alone.
Private source records are not included in this public document.

## Validation and experiment status

The existing overview, evidence and frozen scorecard tests give 11 passes with one
excluded baseline failure. The failure is
`test_bracket_identity_survives_public_cards_with_overlapping_matchup_numbers`:
its expected consolation-guidance phrase is absent on untouched main
`5dfeb036fd756ffed1c9b6d9a6ed84757e611525` as well as this candidate. Both unfiltered
runs produced the same one failure and 11 passes. This unrelated assertion is not
changed by the patch. The focused successful run excludes it explicitly.

The preregistered two-arm gate completed one final-regular-week request from the
same original post-prior-week checkpoint, with 146 memory versions and vectors.
The runtime parent was E06 plus the E04 question instruction; E08 and other later
candidates were absent. Original requests, cutoffs, source assets, settings and
first model messages/tools matched; only this guidance file differed. Both arms
preserved every inherited version and completed their article and memory commit.

The discriminating team scored above the median but below the arithmetic mean,
and its recorded result was a sweep. Both arms preserved that sweep. Control
used the legacy average label without publishing a cutoff, then explicitly ruled
out arithmetic mean in its saved league note. Treatment named the median and
correctly excluded the bonus from postseason games. Neither article published a
numeric threshold. The motivating explicit mean error did not reproduce.

Decision: inconclusive for improved applied-decision accuracy. The independently
supported terminology clarification remains reviewable; no full-season efficacy
promotion or reroll follows. Do not replace the fresh control with an older
failing article. Correct terminology is not a general quality result.

Control used 32 calls, four edits and five closeout turns; treatment used 36 calls,
13 edits and four closeout turns. Costs were $0.15787 and $0.15562, totaling
$0.31349, with no embedding request or new uncertain charge. Both unchanged
articles and complete traces remain private.

A separate adverse finding remains: treatment saved a canonical claim that no
additional first-round pick arrived after an earlier trade, despite a later saved
acquisition. Its fresh source queries covered recent weeks and the earlier trade
window, omitting the intervening acquisition. The article's “since” is less
explicit; the saved summary has a clear false historical anchor. This does not
establish causation by the median guidance and is not hidden by the correct bonus
wording. It motivates a separate historical-scope hypothesis, not another change
in this PR.
