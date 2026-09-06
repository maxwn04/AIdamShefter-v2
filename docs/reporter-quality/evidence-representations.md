# Source relationships and durable trade representations

The evidence catalog preserves executed source values and exact provenance.
Article verification remains advisory: a valid player name and score do not
establish ownership, a completed transaction does not establish a pickup, and
typed trade assets do not certify every sentence of an authored summary.

## Trade payload compatibility

`TradeEventPayload` accepts two mutually exclusive representations:

- Retained events have a top-level sender and receiver franchise UUID, with
  `sender_to_receiver` or `receiver_to_sender` on each asset.
- New source-derived events contain assets with explicit `from_franchise_id`
  and `to_franchise_id`. They have no global sender/receiver or asset direction.

All endpoints must be present and different. Mixing the formats is invalid.
Participants are derived from the assets. Player and pick identities must be
distinct across the transaction, regardless of transfer endpoints. Budget
uniqueness uses the endpoint pair. A pick uses either its canonical UUID or a
complete draft-year, round and original-franchise identity. Resource validation
checks every endpoint and pick origin against the event's competition, and
preserves existing player/pick/receipt reference checks.

Unset additive fields are excluded from serialization. Retained payloads keep
their serialized content, content hashes and semantic sender/receiver roles.
Existing JSON codecs require no migration or rewriting of immutable artifacts.
`resolve_trade_transfers()` normalizes either form for consumers. Event search
documents include every participant and explicit transfer direction for new
events; retained event indexing remains unchanged.

`present_trade()` receives roster and player label callbacks from the calling
memory presenter. Callers scope roster labels to the inspected event's season,
including the original franchise of a natural pick. The helper preserves legacy
omissions and renders every new asset with both endpoint labels. It does not
resolve a historical franchise against an unrelated current display name.

## Source resolution

The event resolver validates selected saved fact bindings, identifies exactly
one completed transaction in the same frozen snapshot and current generation
season, then expands all its assets. It never saves only the selected player.

Missing identity joins remain visible for validation. Each player transfer must
have one outgoing and one incoming source perspective; picks likewise require
one `pick_out` and one `pick_in`. These rows may have different move indexes.
The resolver validates endpoint/perspective agreement before collapsing each
mirrored pair once. Missing, duplicated or conflicting transfers reject the
whole event, including when the defective asset was not selected in the brief.
Provider week grouping and actual source timestamps remain distinct.

## Compact source cards

Transaction queries carry source movement codes, endpoint team labels and roster
keys. Grouping uses roster identity, so identical display names do not merge
participants. Evidence cards expose season-scoped endpoint lookups and retain
the local sent/received perspective. Unknown source directions stay inspectable
as unavailable evidence rather than defaulting to an acquisition.

The transaction overview suppresses only an exact pair of mirrored trade cards
with explicit endpoints and opposite perspectives within the same source
transaction. Ambiguous groups remain visible. Detail inspection retains all
catalog records and stable refs, including both perspectives and every pick.

Each player-score card carries its source team name and roster lookup when
available. A `team_game` query includes both sides; the requested team does not
own every returned player. Existing score precision and source paths survive.

Standings queries distinguish the requested week from `standings_through_week`,
derived from the source playoff start. Standings cards use that regular-season
period and identify their basis and units. Bonus-match leagues count standings
decisions; other leagues count head-to-head games. A postseason query does not
turn the frozen regular-season record or streak into current playoff form.
Game intervals stay separate; bracket evidence establishes advancement.

## Verification boundary

Targeted coverage exercises actual frozen query output, selected source
bindings, a new explicit trade, canonical PostgreSQL commit and typed readback.
Compatibility tests retain two-party payloads and semantic exports. Additional
source cases cover duplicate display names, both-team player scores, unknown
movement and standings cutoff without changing game periods.

Offline replay of retained snapshots checks relationship representation and
response bytes. It does not demonstrate generated article quality, provider
token savings or season-long narrative behavior. Authored summaries remain
inspectable reporting, not automatically verified descriptions of typed assets.
