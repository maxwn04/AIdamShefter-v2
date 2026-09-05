# Evidence contract

Contract version `1` uses `EvidenceRecord` and `EvidenceReader` in
`backend/services/reporter/runner/evidence.py`.

- Invocation sources are `e<turn>_<ordinal>`, assigned from dispatch order before
  execution. Recorder-free direct calls use a separate `direct<N>` namespace.
  Record references append `.r<N>` in source traversal order. They are run-local.
- `resolve(ref)` returns an executed record or `None`; `records_for(source)`
  returns the invocation population. Catalog reads cannot mutate stored evidence.
- Each record identifies tool, subject, season, week range, perspective, typed
  selected fields, original field paths, units, completeness, population and
  meaningful limitations. No support is inferred from transport success.
- A catalog hashed `subject_id` preserves canonical franchise identity across
  renamed season appearances. Lookup arguments use the source's season-local
  numeric roster key and explicit season. Internal UUIDs stay in audit metadata.
- `temporal_kind` distinguishes interval aggregates, cutoff observations and
  unknown SQL semantics. Nested standings cover weeks 1 through the selected
  cutoff independently of a weekly snapshot. Draft-pick year is an asset field,
  never the roster observation season. Player metrics name the player as subject;
  fantasy team is perspective. Paired game scores have separate owning subjects.
- Outcomes distinguish found, partial, not-found and unavailable. Incomplete
  populations cannot prove unrestricted superlatives. SQL and ambiguous semantic
  categories remain diagnostic; a valid reference is never a blanket truth stamp.
- Raw response, internal snapshot/UUID identities, and durable execution ID belong
  in private execution metadata. Public roster lookup keys remain usable.
- Public pages contain at most 40 selected records with `next_offset` and a
  `read_evidence(source, offset, limit, view)` drill-down. Tool/source are shared at the
  envelope level. Oversized scalar fields are omitted with explicit limitations.
  Common season/week/perspective/temporal dimensions live in envelope `scope`;
  those defaults describe the source; the model need not copy them into bindings.
  Weekly overview cards omit player detail; league overview includes format,
  games and standings, with transactions available through their own query.
  `view=detail` retrieves the full catalog; offsets are relative to the chosen
  view, and `catalog_records` reports the unfiltered count. Meaningful caveats
  appear in `limitation_definitions` only for displayed records;
  record `limitation_refs` index that lookup, never a blanket feed warning.
  Public `population_complete` labels comparison completeness explicitly.
  SQL metadata, UUID/hash identities and serialized audit fields remain private;
  SQL selected values are diagnostic and cannot establish complete populations.

Brief bindings select only `ref`, `field`, and `value`. The consumer checks the
selected value and hydrates subject, season, week range and perspective from the
immutable catalog. Stored rich bindings and historical briefs remain readable.
Canonical `data_refs` and numeric summaries derive from selected bindings; neither
is advertised as model input. Compatibility-only old refs/number aliases are
discarded; explicitly supplied old source dimensions still must match.
Binding rejections include a precise repair action. Wrong-field suggestions are
limited to 12 names from that selected record, with an explicit truncation flag;
they never enumerate the catalog. Value/dimension mismatches return the exact
selected source value. Unknown/unavailable refs require available source evidence.
Specialized claims use categories `transaction`, `comparison`,
`superlative`, and `championship`; ordinary facts retain their existing categories.
Comparison bindings require comparable fields for the same subject at distinct
ordered periods. Cross-season interval comparisons require aligned coverage;
listed `roster_members` cutoff observations can compare different cutoff weeks
for the same canonical franchise. They do not establish acquisition timing or
method. Superlatives require an explicit `superlative_direction` of min/max,
optionally `superlative_unique`, complete same-scope populations, and
championship requires playoff outcome evidence. Unsupported specialized shapes
must be narrowed or reported diagnostic, never silently certified.
`superlative_binding={ref,field}` identifies the asserted metric when other
bindings provide context. All bindings still undergo exact source checks.

Only full curated standings populations from standings, league snapshot and
league history currently certify a structured superlative. Ancestor truncation
and applicable game/league-average completeness warnings invalidate that
population. Limited leaderboards, recent-game lists and SQL remain incomplete.
Failed, pending or unknown-status transactions cannot support completed movement.
Directional transaction bindings select actual asset identity or net pick count;
net count does not claim value equivalence between different draft picks.
Transaction cards inherit source status, bid and readable `occurred_at` UTC from
the provider's millisecond creation timestamp. `source_week` labels endpoint
grouping; transaction week interval bounds are unset. Neither grouping nor the
timestamp establishes response-to-loss causality. Game side/result records carry
`sleeper_matchup_number`, the source matchup integer; league snapshots include
`league_average_match` so standings decisions can be distinguished from H2H games.

New facts require field bindings and resolve every source reference. Saved legacy
briefs remain readable with `support_status=legacy_unchecked`; they cannot unlock
new submission until rebound to executed evidence. Successful new facts use
`support_status=traceable`, never a prose truth guarantee. Historical artifact
content is not rewritten.

Dependent brief mutations accept only committed fact/storyline IDs. Errors retain
their existing codes and include accepted/missing IDs, the current brief revision,
and a repair instruction. Missing dependencies never partially mutate the brief
or its managed projection, and are never silently dropped or invented.

Draft checks inspect actual content with bounded targeted diagnostics and retain
article hash/revision plus brief revision. Editing either invalidates the receipt.
Uncertain semantic matches are DIAGNOSTIC and do not prove or block all prose.

Verification inspects up to 30,000 characters, 160 sentence segments and 100
referenced records, returning at most 40 diagnostics and an explicit truncation
flag. Visible source references are checked across the whole article. Submission
refreshes stale checks as guidance. All verification findings, including unresolved
traceability and visible source-reference errors, are advisory and never gate
submission. Receipts explicitly report `submission_blocking=false`. `save_fact`
still validates structured binding inputs at mutation time; artifact revision,
content, immutability and structured brief readiness requirements remain in force.

## Snapshot completion and compatibility

New game derivations require explicit provider `last_scored_leg` or a valid
regular-season result prefix. Score positivity, calendar age and completed-league
status alone do not establish completion. Confirmed zero-score ties are retained;
unknown games stay in source rows with omission warnings. Missing historical
playoff completion may therefore leave narrower available game history.
League-average outcomes only use the completed prefix. No query fallback invents
unplayed ranks or results. Championship flags require the winners bracket.

`SNAPSHOT_DERIVATION_VERSION` participates in new canonical build keys, separately
from source `input_revision` and readable physical schema versions 2/3. New
selection materializes corrected derivations; previously pinned historical
artifacts remain readable and are not silently rewritten.

Fixtures must include real frozen-query adapter outputs through brief and draft:
directional trade assets, per-team records, renamed franchise drill-down, rounded
points, truncated superlative populations, absent history and playoff evidence.
