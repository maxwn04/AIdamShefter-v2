# Memory discovery, callbacks, and evidence contracts

## Memory tool behavior

`search_memory` defaults to all seasons in the frozen snapshot. Season, team,
kind, status and week filters narrow candidates before ranking and limiting.
Team selectors use `franchise:<UUID>` and include that franchise's season-roster
projection aliases. Names may resolve across available seasons; reused names
belonging to different franchises require a season or durable selector.
Callbacks can also match the teams on their direct storyline or origin event,
using that parent's eligible version at the pin. This does not recursively
inherit teams or change stored historical projections.

Search preserves complete narrative summaries while omitting nested evidence by
default. `inspect_memory(memory_handle, view, offset, limit)` selects detail,
history or evidence. History stops at the selected version and pinned revision;
history/evidence handles remain read-only even after a current card is recalled.
The pin defines narrative knowledge: a generation's source observation cutoff
must not hide the prior generation's output merely because it was recorded later.
Frozen season/week limits still apply to discovery and inspection.

Text discovery now composes lexical and available semantic matching under the
[hybrid discovery contract](semantic-discovery.md). Historical narrative versions
may supply a better lead than the latest summary and remain explicitly read-only.
Semantic capability is opt-in and derived indexes must be built explicitly.
Search reports degraded semantic coverage separately from a genuine no-match;
structured recovery remains available. Real paraphrase quality requires an
approved retrieval-only comparison and does not follow from deterministic tests.

`upsert_storyline_memory_card` merges supplied subjects into existing subjects
and preserves their roles by default. `subjects_mode="replace"` intentionally
removes omitted subjects, including clearing them with an empty replacement.
Omitted state, origin and existing evidence remain preserved.

`update_memory_callback` accepts a selected handle, resolve/reschedule/defer,
and a reason. Reschedule requires a future week and preserves the original source
event. Defer records an uninvestigated outcome without a canonical mutation.
Each callback still permits one semantic update per run; a later defer cannot
overwrite a successfully selected resolution or reschedule. Failed operations
leave prior proposals and disposition records intact. Completion stays
argument-free and does not require dispositions for every due callback.

This delivery extends the reporter over the retained season baseline. It supersedes
the earlier ownership split in `coordination.md` and explicit-season-only discovery
proposal. Existing generation finalization and immutable artifact contracts remain.

Article quality, useful discovery and faithful memory outcomes are the primary
acceptance criteria. Bytes, tokens and cost are informational in this delivery.
Compact presentation is useful when it improves relevance or understanding; it
must not remove relationships, caveats or context needed for good reporting.

## Ownership and shared seams

| Surface | Owner |
| --- | --- |
| Memory query resources/services, current recall, memory handles and inspection | Memory querying and callback lifecycle |
| Storyline subject/state updates, callback dispositions and closeout guidance | Memory querying and callback lifecycle |
| `memory_tools.py`, `memory_presentation.py` and their existing tests | Memory querying and callback lifecycle |
| Evidence presentation, source-derived event resolver, trade payloads/resources | Evidence and memory representations |
| Evidence tests and dedicated representation compatibility helpers | Evidence and memory representations |
| Shared contracts and combined acceptance review | Coordinator |

Owners agree interfaces before editing. Trade rendering changes needed in memory
presentation are integrated by the memory owner after the representation interface
is settled. Separate worktrees and branches preserve independently reviewable
changes. No simulation runtime, frozen export, or legacy implementation is edited.

The representation owner also owns `search_documents/builders/event.py`, curated
transaction/league/team queries, and any required generated frontend API types.
The memory owner owns other search modules and retrieval/history services. Tests
follow production ownership; existing memory-tool/presentation tests have one
owner. Operational workspaces may be junctions, so each task uses a distinct
subdirectory within the shared ignored context.

## Discovery and identity

Automatic memory is compact current working context, including pinned visibility
and bounded active/due work. Broader discovery uses a query tool returning compact
matches and handles for selected history/evidence inspection. Season, franchise,
kind, status and period are optional discovery filters. An omitted season permits
cross-season discovery within the selected competition and memory revision.

Durable franchise identity connects renamed teams. Presentation includes usable
team selectors and season-aware labels; display-name guessing is unnecessary.
The stable selector is `franchise:<UUID>`. Team filters constrain results even
when a text query is also supplied; matching text cannot bypass a team filter.
Historical reporting and hypotheses remain distinguishable from verified frozen
source evidence. Historical discovery does not grant historical write access.
Inspection and ranking must respect pinned revision visibility and temporal bounds.

Routine storyline updates preserve canonical identity, origin, prior state, team
relationships and evidence. Intentional subject removal is explicit. Updates
use `subjects_mode="replace"` only for intentional subject replacement; routine
updates merge relationships. `inspect_memory` supports selected detail, history
and evidence with bounded pagination and read-only superseded-version handles.
Retrieval choices are tested against focused narrative questions and paraphrases; vector or
hybrid infrastructure requires a demonstrated useful gap in structured/lexical
discovery and an explicit maintenance/version-visibility contract.

## Callback lifecycle

Resolve, reschedule and defer apply to the selected callback through successful
buffered mutations. Runtime derives bookkeeping from that mutation. Defer remains
open and uninvestigated; it does not assert an answer. Existing atomic publication,
read-only/backtest behavior and closeout constraints remain intact.

No mandatory disposition gate is added for every due handle. No forced article
mention, separate duplicate completion receipt, unseen reminder closure, automatic
satisfaction, or parent-resolution cascade is introduced.

## Evidence and durable events

Transaction assets show their actual origin and destination, with stable franchise
identity, complete pick identities and explicit add/drop direction. Multi-party
trades preserve every participant and asset transfer. Retained two-party payloads
and immutable artifacts remain readable without rewriting history.

`resolve_trade_transfers(details)` returns typed assets with explicit
`from_franchise_id` and `to_franchise_id`. Payloads accept either the complete
legacy pair/direction form or complete explicit endpoints, rejecting mixed,
partial, duplicate or self transfers. New source-derived events use endpoints;
participants derive from them. The representation-owned `present_trade` helper
returns participant `{label, role}` and asset `{label, direction}` dictionaries.
The memory presenter supplies roster/player label callbacks using the inspected
event's season. Legacy serialized payloads remain unchanged.

Player production retains the player's team relationship and period. Standings
decisions distinguish head-to-head and bonus units. Regular-season records retain
their actual terminal week and do not imply current playoff form or seeding stakes.
Bracket phase and advancement remain distinct from score comparison.

Unknown references, absent values, mismatched identities and unavailable sources
still fail meaningful source validation. Article verification remains advisory;
typed bindings do not establish the truth of arbitrary authored summaries.

## Acceptance and limits

Targeted tests cover actual query-to-presentation-to-selected-binding-to-event
boundaries, renamed cross-season discovery, compact results with selective
inspection, historical write protection, subject/state preservation, and callback
resolve/reschedule/defer without cascades. Independent non-author review checks
each implementation slice and combined shared seams.

Retained source cases include reversed transactions, omitted draft capital,
three-party trades, opposing-player attribution and frozen playoff standings.
Review article and saved-memory failures alongside mechanics and response size.
Offline replay establishes interface behavior; it does not establish new article
quality, provider token use, or season-long callback behavior. New paid evaluation
and merging are separate user decisions after reviewable PRs.
