# Median bonus terminology: offline candidate

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

No paid comparison has run. The active original-storyline-context experiment is
unchanged. A future comparison must freeze its parent, checkpoint, cutoff and
evaluation before dispatch. It should distinguish merely repeating “median” from
correctly explaining actual standings decisions, retain source results, and check
that postseason outcomes are not assigned an invented bonus decision. It must not
claim improved general article quality from a terminology correction.
