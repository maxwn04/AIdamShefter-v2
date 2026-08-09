# Database Design Decision Log

This is an append-only collaboration record for settled decisions, explicit
user feedback, and decisions that materially constrain more than one database
namespace. Detailed schema rationale belongs in the namespace documents.

## Entry Format

Each entry records:

- a stable decision identifier;
- the date and status;
- the decision or feedback;
- why it was settled;
- consequences for downstream design work.

When a later entry explicitly supersedes an earlier one, the later entry is the
implementation contract. Earlier entries remain here to preserve the reasoning
history.

## Decisions

### DB-001 — Replace existing persistence without compatibility work

**Date:** 2026-08-08  
**Status:** Settled  
**Source:** User direction

The new database is a clean replacement for the current in-memory datalayer,
SQLite reporter-memory store, and filesystem generation outputs. Existing data
is ephemeral and can be regenerated.

**Consequences:**

- Do not design legacy import migrations.
- Do not add dual-read or dual-write compatibility paths.
- Do not retain old schema shapes or IDs solely for compatibility.
- Preserve proven product behavior and test intent, not old persistence APIs.
- Establish a clean Alembic baseline for the new database.

### DB-002 — Use one modular PostgreSQL database

**Date:** 2026-08-08  
**Status:** Settled  
**Source:** Architecture review

Use one physical PostgreSQL database with four logical namespaces: `core`,
`sleeper`, `memory`, and `reporting`. Keep code and ownership boundaries strong
without introducing microservices or separate sources of truth.

**Consequences:**

- Cross-namespace audit queries and foreign relationships are allowed.
- There is one ordered migration history.
- Physical separation is deferred until a measured operational or security need
  appears.

### DB-003 — Target Supabase-hosted PostgreSQL

**Date:** 2026-08-08  
**Status:** Settled  
**Source:** User direction

The product database will be hosted in Supabase PostgreSQL. Database access is
still owned by the backend; use of Supabase-generated APIs, authentication, RLS,
storage, or realtime features is not implied and must be chosen deliberately.

**Consequences:**

- Infrastructure design must cover direct versus pooled connections, SSL,
  migration connectivity, application roles, secrets, backups, extensions, and
  Supabase-specific operational constraints.
- Credentials must be supplied through environment configuration and never
  committed.
- This design phase will not connect to or mutate the Supabase project.

### DB-004 — Design and harden schemas before implementation

**Date:** 2026-08-08  
**Status:** Settled  
**Source:** User direction

Complete a reviewable schema design for every namespace and the shared database
infrastructure before adding manager code, services, ORM models, or migrations.

**Consequences:**

- Namespace documents must cover invariants, relationships, temporal semantics,
  indexing, deletion, provenance, and extension points.
- The eventual implementation should be delivered as a GitHub PR stack whose
  layers define database infrastructure, migrations, and model/schema files.
- The present work produces design documents only.

### DB-005 — Keep manager and service implementation out of schema scope

**Date:** 2026-08-08  
**Status:** Settled  
**Source:** User direction

Resource managers and application services remain important architectural
boundaries, but they are not part of this schema-hardening phase.

**Consequences:**

- Schema documents may state ownership and required access patterns.
- They should not prescribe manager method signatures or service implementation
  details.
- ORM model and migration work begins only after the schema review is accepted.

### DB-006 — Authenticate at boundaries; enforce resource scope below them

**Date:** 2026-08-08  
**Status:** Settled  
**Source:** User feedback and architecture review

Authentication belongs in API or process-boundary adapters. Persistent resource
access later receives an already-resolved actor and scope so competition
isolation and mutation provenance apply equally to API, worker, CLI, and reporter
execution paths.

**Consequences:**

- Database design should retain ownership and provenance fields needed for
  resource scoping and auditing.
- The initial local product does not require enterprise RBAC.
- Supabase Auth and RLS are not assumed by the schema unless separately adopted.

### DB-007 — Make `core` the sole owner of durable and provider identity

**Date:** 2026-08-08  
**Status:** Settled  
**Source:** Cross-namespace schema review

`core` owns competitions, competition seasons, franchises, season roster slots,
managers, and qualified provider league/roster/account identities. The canonical
roster name is `season_roster_slot`; other namespaces must not create parallel
identities for those resources.

**Consequences:**

- Sleeper tables reference `core.provider_*` identities and store only the
  observation-backed versions of their attributes.
- Unresolved observations are retained in provider-scoped staging/quarantine;
  canonical facts require confirmed core scope.
- `core` remains a dependency root with no foreign keys into other namespaces.

### DB-008 — Use an explicit cross-namespace football coordinate

**Date:** 2026-08-08  
**Status:** Settled  
**Source:** Cross-namespace schema review

Football-effective coordinates use a competition season, optional phase
(`preseason`, `regular`, `postseason`, or `offseason`), optional non-negative
week, and optional exact effective timestamp. Timestamp ranges are half-open;
week bounds are inclusive.

**Consequences:**

- Domain/effective time remains distinct from observation/recorded time.
- Week zero can represent preseason/before-Week-1 state where appropriate.
- A run still requires exact data-snapshot and memory-checkpoint membership;
  these coordinates alone are not a replay boundary.

### DB-009 — Standardize baseline SQL types

**Date:** 2026-08-08  
**Status:** Settled  
**Source:** Infrastructure and namespace review

Use application-generated UUIDv4 primary keys, database-generated UTC
`timestamptz` creation times, text with named check constraints for bounded
states, `numeric(12,4)` for fantasy scores, and `numeric(20,10)` plus explicit
currency for prices and calculated costs.

**Consequences:**

- Provider and agent labels remain attributes, never primary keys.
- UUID ordering has no meaning; explicit timestamps and sequences define order.
- Native PostgreSQL enums and binary floating-point costs/scores are excluded
  from the baseline.

### DB-010 — Keep application schemas private and let Alembic own DDL

**Date:** 2026-08-08  
**Status:** Settled  
**Source:** Supabase infrastructure review

Alembic is the only application migration history. `core`, `sleeper`, `memory`,
and `reporting` remain private behind FastAPI, with the Supabase Data API
disabled or unable to expose them. The baseline does not use RLS because no
Supabase JWT identity is carried into direct backend database sessions.

**Consequences:**

- Supabase CLI migrations and dashboard-authored schema changes cannot also own
  these objects.
- Migrations use a dedicated migrator/owner role; API and worker use
  least-privilege runtime roles rather than `postgres` or `service_role`.
- Direct connections are preferred for migrations and persistent processes;
  Supavisor session mode is the IPv4 fallback. Transaction mode is reserved for
  a future serverless need.

### DB-011 — Retain exact frozen data artifacts and use hybrid object storage

**Date:** 2026-08-08  
**Status:** Settled  
**Source:** Backtesting and infrastructure review

Every sealed factual snapshot referenced by a retained generation run keeps its
exact content-addressed frozen SQLite artifact. Small structured content remains
inline in PostgreSQL; large immutable payloads and binaries use private object
storage with database hashes, sizes, locators, and retention state.

**Consequences:**

- An 8 MiB starting threshold is an operational default, not a schema invariant.
- A referenced object's bytes cannot be garbage-collected.
- Database and object-storage backups must be restored and verified together.

### DB-012 — Keep durable memory state small; put run telemetry in reporting

**Date:** 2026-08-08  
**Status:** Reporting ownership retained; memory model superseded by DB-025  
**Source:** Cross-namespace schema review

Memory owns branches, commits, sealed checkpoints, stable items, complete
immutable versions, version-owned relationships, durable evidence, and accepted
trigger state/firings. Reporting owns run-scoped searches, ranked candidates,
uses/rejections, verification attempts, and trigger-evaluation attempts.

**Consequences:**

- A complete memory version carries its full relationship set; the baseline
  does not add a second `links`/`link_versions`/`checkpoint_links` versioning
  system.
- Search documents remain a rebuildable memory projection, while execution
  traces live with other run telemetry.
- This is a versioned relational model, not a general event store.

### DB-013 — Evidence targets immutable facts or content

**Date:** 2026-08-08  
**Status:** Narrowed by DB-024 for the simplified baseline  
**Source:** Cross-namespace schema review

Evidence may reference an observation-specific Sleeper fact version, an exact
endpoint observation and retained payload locator, an immutable reporting tool
result/brief-fact/artifact revision, or another memory version. It may not cite
only a mutable logical matchup/transaction identity or an unenforced kind/ID
pair.

**Consequences:**

- Evidence-bearing payloads are retention-pinned.
- One typed `memory.evidence` contract is reused by verification records rather
  than duplicating polymorphic targets.
- Corrections remain distinguishable from the older value actually seen by a
  historical run.

### DB-014 — One run has at most one final memory output

**Date:** 2026-08-08  
**Status:** Superseded by DB-025  
**Source:** Reporting and memory review

A generation run reads one sealed memory checkpoint and may produce at most one
final applied memory mutation batch, commit, and output checkpoint. Disabled,
skipped, rejected, and conflicted outcomes remain explicit.

**Consequences:**

- A run never reads its own output checkpoint.
- Backtest and experiment output stays on an isolated branch.
- The reporting mutation ledger records the output result; memory records the
  producing run on the commit. A redundant direct output pointer on the run row
  is unnecessary.

### DB-015 — Put durable draft-pick identity in `core`

**Date:** 2026-08-08  
**Status:** Settled  
**Source:** Cross-namespace schema review

Expected dynasty draft-pick assets outlive a particular Sleeper league and are
therefore core competition identities. Sleeper owns observed trades, traded-pick
snapshots, and ownership projections that reference those assets.

**Consequences:**

- Provider pick IDs are qualified by their provider scope and are never treated
  as globally unique.
- Original-franchise reconciliation is correctable rather than embedded as an
  irreversible fact when identity is unresolved.

### DB-016 — Centralize ORM models under `backend/database`

**Date:** 2026-08-08  
**Status:** Settled  
**Source:** User feedback and adversarial review

All SQLAlchemy ORM/table definitions live in namespace subpackages under
`backend/database/models/`. Resource objects and managers stay together under
`backend/resources/<resource>/`.

**Consequences:**

- Alembic imports one obvious centralized metadata registry.
- Database relationships are easy to inspect without opening every manager.
- Namespace subpackages preserve ownership; a single giant models file and a
  generic CRUD repository are still rejected.
- ORM rows do not cross into services, routes, workers, or reporter tools.

### DB-017 — Reduce core to four Sleeper-specific identity tables

**Date:** 2026-08-08  
**Status:** Settled; supersedes DB-007 and DB-015 where they conflict  
**Source:** User feedback and adversarial review

Core contains only competitions, ordered competition seasons, franchises, and
season rosters. Sleeper league/roster IDs are explicit columns. Managers,
provider registries, aliases, merges, reconciliation candidates, and core draft-
pick assets are deferred.

**Consequences:**

- `competition_seasons` keeps `season_year` and `sequence_number`, but no
  starts/ends/status.
- A franchise has display name and optional archive time, with no merge state.
- `season_rosters` is the seam that preserves cross-season franchise identity.
- Sleeper users supply manager display data; future person identity can map onto
  those IDs additively.
- Draft-pick ownership remains a Sleeper-normalized feature close to the current
  datalayer.

### DB-018 — Remove fantasy phase and simplify memory time vocabulary

**Date:** 2026-08-08  
**Status:** Settled; memory-snapshot wording superseded by DB-025  
**Source:** User feedback and domain review

Memory and generation records use competition season, optional week, optional
exact occurrence/cutoff time, and database-recorded time. There is no phase
column; playoff context is derived from Sleeper league settings and week.

**Consequences:**

- Tool-facing temporal language stays close to the current week-based product.
- Exact data and memory snapshot IDs—not temporal predicates alone—remain the
  historical visibility boundary.

### DB-019 — Make Sleeper persistence request-oriented

**Date:** 2026-08-08  
**Status:** Settled  
**Source:** User proposal and adversarial review

Persist refreshes, every API request, and hash-deduplicated raw payloads. Maintain
a latest normalized PostgreSQL view close to the current datalayer. Historical
generation snapshots select eligible old API requests and re-run the existing
normalizers into a frozen SQLite artifact.

**Consequences:**

- Idempotent merging occurs per complete endpoint scope.
- Failed/incomplete requests do not replace normalized current rows.
- Every normalized entity does not require its own bitemporal version system.
- Existing games/standings/team profiles remain derived SQLite tables, not a new
  persistent projection framework.

### DB-020 — Replace memory branches with child snapshots

**Date:** 2026-08-08  
**Status:** Superseded by DB-025  
**Source:** User feedback and memory alternatives review

Memory uses stable items, immutable complete versions, full memory snapshots,
snapshot membership, and one canonical head per competition. It has no named
branches, commits, merges, or publication workflow tables.

**Consequences:**

- A generation reads one snapshot and may create one child snapshot.
- Backtest children do not advance canonical memory; rolling backtests chain
  child snapshots.
- Fake competition IDs are rejected because they corrupt league identity.
- Git is deferred to an optional deterministic JSON audit mirror, not persistence.
- Storyline priority and importance collapse into one `salience` value.

### DB-021 — Center reporting on generations and tokens

**Date:** 2026-08-08  
**Status:** Settled; extended by DB-025 with one evaluation workspace  
**Source:** User feedback and runner-code review

The baseline reporting schema contains generations, AI calls, tool calls,
artifacts, and artifact versions. The generation row stores typed snapshot/
cutoff fields plus its immutable JSONB input manifest.

**Consequences:**

- One `ai_calls` table records every actual request, including retries and
  fallback attempts, with exact messages/responses and token categories.
- The database stores no pricing catalogs, calculated costs, or cost summaries;
  dashboards calculate current/projected cost from tokens and model identity.
- Articles are generic versioned artifacts; briefs have no specialized schema.
- Presets, jobs/leases, event streams, memory-search telemetry, experiments,
  comparisons, and evaluations are deferred.
- Frontend progress uses generation status/current-turn fields and polling.

### DB-022 — Store fantasy scores as exact decimals

**Date:** 2026-08-08  
**Status:** Settled; refines DB-009  
**Source:** User question, current code, and Sleeper API review

Canonical fantasy points use `numeric(12,4)` normalized through `Decimal` rather
than Python float or integer hundredths.

**Consequences:**

- Values remain in natural point units for SQL and tools.
- The schema does not assume Sleeper will always cap every custom scoring result
  at two decimal places.
- Integer scaling and conversion code are unnecessary.

### DB-023 — Prefer additive seams over speculative tables

**Date:** 2026-08-08  
**Status:** Settled; DB-025 approves one concrete evaluation workspace  
**Source:** User direction

The clean baseline intentionally defers features that are not required for the
first complete platform, even when they are plausible future needs.

**Consequences:**

- “Future extensibility” means stable IDs, clear ownership, JSON/version seams,
  and additive migration paths—not empty tables or complex workflows today.
- Implementation agents must not resurrect manager churn, provider abstraction,
  branch/commit memory, durable scheduling, presets, pricing, or experiment
  schemas without a new reviewed decision.

### DB-024 — Harden the simplified snapshot and request boundaries

**Date:** 2026-08-08  
**Status:** Settled for factual snapshots; memory portion superseded by DB-025  
**Source:** Final adversarial cross-namespace audit

Keep the simplified architecture, but enforce the few ownership boundaries it
depends on. Sleeper has one concurrency-safe normalized head per endpoint scope;
pending generations resolve and freeze inputs before running; ready data/memory
snapshots are immutable and competition-scoped; a memory output is owned only by
its unique producing-generation reference.

DB-013 is narrowed for the baseline: fact/event versions have typed primary
tool-call and API-request receipts, while additional JSON source hints are
non-authoritative. A generalized typed evidence graph remains deferred.

**Consequences:**

- Empty endpoint responses have durable current-state ownership, and an older
  request finishing late cannot overwrite a newer normalized scope.
- A pending generation may exist before snapshot resolution; `running` and
  `succeeded` require ready inputs and a sealed manifest.
- Cross-competition IDs cannot be combined through application mistakes.
- There is one output-memory pointer, on `memory_snapshots`, rather than a
  redundant bidirectional relationship.
- Every non-root memory revision/output has generation provenance; setup creates
  one empty root/head atomically.
- Ready snapshot request membership, hashes, and artifact locators cannot change.

### DB-025 — Keep canonical memory linear and evaluations outside it

**Date:** 2026-08-08  
**Status:** Settled; supersedes DB-020 and the memory-snapshot portions of DB-024  
**Source:** User feedback and evaluation-needs review

Canonical memory is a strict sequence of atomic revisions. Memory versions record
the revision that introduced them and, once replaced, the later revision that
retired them. There are no canonical memory snapshots, membership copies,
sibling states, branch heads, or merge behavior.

Longitudinal backtests use at most one active reporting-owned evaluation workspace
per competition. The workspace is serialized as immutable JSON artifacts between
simulated generations and never writes alternative rows into canonical memory.

**Consequences:**

- Ordinary model, prompt, tool, retrieval, token, and article comparisons reuse a
  pinned canonical revision and need no mutable alternative memory.
- Discarding an evaluation closes its workspace with no canonical mutation.
- Promotion is fast-forward only: the canonical current revision must still equal
  the workspace base, and the final diff becomes one new canonical revision.
- Historical simulations based on an older revision cannot be promoted. There is
  no rebase, three-way merge, or conflict-resolution UI.
- Multiple variants run sequentially from the same base and are compared through
  generation logs and artifacts; parallel/named workspaces are deferred.
- Replacing canonical history would be a separately reviewed full rebuild, not a
  promotion option.

## Current Implementation Decisions

The current baseline is defined by DB-001 through DB-006, DB-010 through DB-011,
DB-016 through DB-026, and DB-028. Within that set, later entries explicitly take
precedence. DB-017 supersedes the larger identity/provider designs, DB-020
supersedes branch/commit memory, DB-021 supersedes workflow/pricing-heavy
reporting, DB-024 narrows the former evidence design and hardens factual snapshot
boundaries, and DB-025 replaces persistent alternative memory with a linear
canonical revision plus one reporting workspace. DB-028 moves product-semantic
validation out of DDL while retaining relational, concurrency, storage-shape,
and sealed-history guarantees.

## Pending Decisions

No implementation-blocking schema decisions remain. Environment confirmations
and operational retention durations are tracked in `status.md`; promote any
future design change here before implementation diverges from the contract.

### DB-026 — Publish the implementation stack with GitHub CLI

**Date:** 2026-08-08  
**Status:** Settled  
**Source:** User direction

Build and publish the database-only PR stack with the GitHub CLI's `gh stack`
workflow. Graphite is not set up for this repository and must not be used for
this stack.

**Consequences:**

- Each stack layer is committed on its own `codex/` branch managed by
  `gh stack`.
- Each pull request shows only its incremental changes relative to the parent.
- Stack initialization, branch addition, and publication use `gh stack`; PR
  metadata and final verification use the relevant `gh pr` commands.

### DB-027 — Fix physical boundary-validation details consistently

**Date:** 2026-08-08  
**Status:** Settled  
**Source:** Implementation review

Use `1900..3000` as the practical inclusive football season-year range and
reject blank required names and external identifiers after trimming. When an
association table in the approved contract does not prescribe a usable physical
primary key, use an application-generated UUID surrogate without giving it
domain meaning.

**Consequences:**

- Core and football-coordinate checks use the same explicit year boundary.
- Required display names and Sleeper identifiers cannot contain only whitespace.
- Surrogate association-row IDs exist only for ORM identity and referential
  mechanics; ordering and product identity still come from documented columns.

### DB-028 — Keep product semantics in application validation

**Date:** 2026-08-08  
**Status:** Settled; supersedes DB-009, DB-024, and DB-027 where they require
semantic database checks  
**Source:** User feedback and implementation review

Use a lean hybrid integrity boundary. PostgreSQL owns relational identity,
scope isolation, uniqueness needed for concurrency, unambiguous storage shapes,
and sealed-history immutability. Pydantic resource objects and manager/service
transactions own product semantics and readable validation errors.

**Database-enforced baseline:**

- primary keys, schema-qualified foreign keys, `NOT NULL`, and essential natural
  uniqueness;
- composite foreign keys that prevent IDs from different competitions or
  seasons being combined;
- partial uniqueness for concurrency guarantees such as one active workspace,
  one successful AI call per turn, one final artifact version, and one current
  scope/revision pointer;
- only storage-shape checks needed to interpret a row unambiguously, including
  exactly one payload location and exactly one resolved generation memory input;
- append-only or sealed immutability for canonical revisions, ready factual
  snapshots and their membership, terminal call records, and final artifacts.

**Application-enforced baseline:**

- bounded status/type values, football ranges, salience, counts, durations,
  nonblank text, and JSON top-level shapes;
- timestamp ordering, lifecycle transitions, completeness and eligibility;
- hash verification, typed-memory content matching, evidence policy, and
  fast-forward promotion workflow rules.

**Consequences:**

- DDL does not duplicate the application state machine through broad check
  constraints or policy-heavy triggers.
- The database-only stack may temporarily lack semantic enforcement that lands
  with the later Pydantic resource-object and manager/service stack.
- Tests in this stack focus on relational isolation, concurrency uniqueness,
  unambiguous persisted shapes, and immutable history. Semantic validation tests
  belong with the later application objects and workflows.
- DB-027's surrogate-ID choice remains settled; its year-range and nonblank-text
  enforcement move to application validation.
