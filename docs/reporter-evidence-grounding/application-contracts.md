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
- Outcomes distinguish found, partial, not-found and unavailable. Incomplete
  populations cannot prove unrestricted superlatives. SQL and ambiguous semantic
  categories remain diagnostic; a valid reference is never a blanket truth stamp.
- Raw response, internal snapshot/UUID identities, and durable execution ID belong
  in private execution metadata. Public roster lookup keys remain usable.

Brief bindings select `ref`, `field`, `value`, `subject`, `season`, `week_from`,
`week_to`, and optional `perspective`. The consumer checks these against the actual
record. Specialized claims use categories `transaction`, `comparison`,
`superlative`, and `championship`; ordinary facts retain their existing categories.
Comparison bindings require comparable fields for the same subject at distinct
ordered periods. Superlatives require complete same-scope populations, and
championship requires playoff outcome evidence. Unsupported specialized shapes
must be narrowed or reported diagnostic, never silently certified.

Draft checks inspect actual content with bounded targeted diagnostics and retain
article hash/revision plus brief revision. Editing either invalidates the receipt.
Uncertain semantic matches are DIAGNOSTIC and do not prove or block all prose.

Fixtures must include real frozen-query adapter outputs through brief and draft:
directional trade assets, per-team records, renamed franchise drill-down, rounded
points, truncated superlative populations, absent history and playoff evidence.
