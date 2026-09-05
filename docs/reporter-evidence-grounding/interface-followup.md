# Evidence interface followup

Duplicating source references, numeric labels, and identity dimensions creates
avoidable fact-repair work. Interleaving player detail with game scores makes
weekly orientation require unnecessary paging. Compact selections and purposeful
views address those interface problems while retaining source checks.

## Contract

- The model selects bindings using ref, field, value. Runtime derives immutable
  subject, season, period, perspective, references, and numeric summaries.
  Exact selected value mismatches and unavailable references remain errors.
- A superlative may identify the asserted binding explicitly; contextual fields
  remain checked for traceability without becoming additional extrema assertions.
- Weekly matchup summaries present all matchup sides and results before player
  detail. The complete executed catalog and private raw audit remain available.
  Existing team_game and read_evidence support deliberate detail retrieval.
- Standings and transaction views omit metadata-only cards. Transactions show
  readable UTC source timestamps and source-week grouping, with per-record
  completion status. Week grouping does not establish postgame timing or cause.
- Caveat definitions apply only to the displayed records referencing them;
  warnings from other rows cannot contaminate a completed transaction.
  `population_complete` concerns comparison coverage, while transaction `status`
  establishes whether listed movement is confirmed complete.
- Prose diagnostics remain advisory. No added prose regex or truth engine.
- Callbacks, storylines, and outlines require successfully saved dependencies.
  Rejections return accepted/missing IDs, current brief revision, and concrete
  repair instructions, without changing state or silently dropping dependencies.
- Binding repairs suggest at most twelve fields from the selected record, never
  the whole catalog. Wrong values return the actual selected value with a repair
  instruction; unknown/unavailable references still require available evidence.

## Boundaries and validation

The interface owns reporter evidence presentation and brief selection. Source
queries expose the actual matchup number and league-average format without
changing game derivation. Generation, simulator, memory lifecycle, frozen
evaluation runtime, and paid provider execution are separate responsibilities.

Validation uses targeted tests and local replay of retained raw query shapes.
Public byte counts and score availability measure interface differences, not
paid editorial quality. Transaction cards can grow per page when they carry more
useful movement, status, and timestamp detail. Optional player research still
requires deliberate retrieval. Lower orientation cost does not establish lower
total provider usage or better articles.

Replay must preserve selected values and references, independently decode tool
result representations, and avoid inferring prose intent or automatically choosing
specialized metrics. Wrong categories or unselected movement remain meaningful
repair cases. Recorded source data, export identifiers, current validation counts,
and operational measurements belong in ignored execution notes.
