# AIdam Platform Architecture

**Status:** Proposed

**Scope:** Product structure, backend boundaries, persistence, and execution

**Database target:** PostgreSQL, with frozen SQLite generation snapshots

## Summary

AIdam is evolving from a command-line reporter with an ephemeral factual data
layer and a separately persisted memory file into a complete local-first
product. The product needs to persist and connect:

- Sleeper source observations and normalized fantasy-football facts;
- dynasty leagues whose identity spans multiple Sleeper league IDs;
- reporter storylines, facts, events, triggers, and their history;
- generation requests, configurations, articles, briefs, and intermediate
  artifacts;
- model calls, tool calls, token usage, latency, and cost;
- reproducible data and memory inputs for comparisons and backtests.

The proposed architecture is a **modular monolith** with two primary source
directories:

```text
backend/
frontend/
```

The backend uses one primary PostgreSQL database, one migration history, and
clear resource and service boundaries. A generated, cutoff-safe SQLite database
may still be used as a read-only input to an individual generation. It is a
reproducibility artifact and safety boundary, not a second source of truth.

This change intentionally preserves the reporter's current strengths: the
single-loop runner, brief-first research, persistent narrative continuity,
curated data tools, and guarded SQL exploration. The goal is to place those
capabilities inside a durable product rather than redesign the agent loop.

The hardened database contract, namespace designs, implementation order, and
decision record live under [`docs/database/`](database/overview.md). Those
documents are authoritative for table-level implementation; this document owns
the broader application structure and responsibility boundaries.

## Motivation

The current architecture works well for proving the reporter behavior, but its
storage boundaries make the next stage of the product difficult.

### Persistent state is fragmented

Sleeper data is loaded into a new in-memory SQLite database for each execution.
Reporter memory is stored in a separate SQLite file, while articles, briefs,
and run logs are written as files named primarily by week. There is no durable
identity connecting an article to its exact data snapshot, memory state, model
calls, tool evidence, and token usage.

This makes it unnecessarily difficult to answer questions such as:

- Which generation created or changed this storyline?
- Which facts and tool results support this article?
- What model actually handled each turn after retries or fallbacks?
- How many tokens did the generation use, and what would those tokens cost under
  a selected current or projected price configuration?
- Are two articles comparable, or did they use different data or memory?
- What could the reporter have known at a particular historical point?

### The product needs identities that Sleeper does not provide directly

A dynasty league is a continuous product concept, while Sleeper represents its
seasons with different league IDs. Team identity can also outlive a particular
season roster ID, manager, or display name. AIdam therefore needs durable
competition, season, and franchise identities of its own, mapped to the
corresponding Sleeper league and roster IDs.

### Backtesting needs explicit temporal boundaries

Filtering events to a football week is not the same as recreating what was
known at that time. Current roster membership, player status, league settings,
and pick ownership may reveal information from later in the season. Memory has
the same problem when its latest state is read during an older-week replay.

Every generation needs immutable input metadata, including a domain cutoff, a
knowledge cutoff, a factual data snapshot, and either an exact canonical memory
revision or an immutable evaluation-workspace artifact.
The reporter should execute against a physically constrained data view so that
curated tools and free-form SQL cannot reveal future data.

### The product needs more than a CLI

The desired UI needs to trigger and configure generations, inspect memory, audit tool
behavior, render prior articles, compare outputs, and analyze quality against
token usage/projected cost. Those capabilities need durable generation and
resource APIs rather than a
collection of output files.

## Architectural Goals

1. Create one durable source of truth for application state.
2. Preserve strong boundaries between persistence, resource access, business
   workflows, transport, and reporter execution.
3. Make every generation reproducible and auditable.
4. Support dynasty identity across seasons and provider league IDs.
5. Support current generations, retrospective analysis, historically faithful replay,
   and controlled model comparisons.
6. Keep the application easy to run locally while leaving a straightforward
   path to managed cloud infrastructure.
7. Keep the current reporter loop largely unchanged behind stable interfaces.

## Non-Goals

- Splitting the application into microservices.
- Designing every database table and column in this document.
- Building enterprise authentication or RBAC for the initial local product.
- Rewriting the reporter loop as part of the persistence restructuring.
- Migrating ephemeral or easily regenerated local data into the new schema.
- Building a general-purpose event-sourcing framework.

## Replacement and Compatibility Policy

This rearchitecture is an intentional **rip-and-replace** of the current local
storage implementations. Existing Sleeper snapshots, reporter-memory SQLite
files, generated output files, schema versions, and persistence APIs do not
create compatibility requirements for the new database.

Database and application design work should therefore optimize for a clean,
coherent target architecture rather than preserving existing rows or storage
shapes. In particular, implementation work should not add:

- compatibility shims for the current SQLite schemas;
- dual reads or dual writes between old and new stores;
- migrations that import existing local context or output files;
- legacy identifiers solely to preserve regenerated data;
- transitional abstractions whose only purpose is maintaining the old storage
  APIs.

The behaviors that already work well remain requirements: grounded factual
queries, narrative continuity, brief-first generation, guarded SQL, and the
reporter tool contracts. Existing fixtures and tests may be adapted to validate
those behaviors against the new architecture, but the persisted data itself can
be discarded and regenerated.

This freedom applies while constructing the new baseline. Once the new schema
is adopted as the product database, subsequent changes must use normal
forward-only migration discipline and preserve data created under that new
baseline.

## System Shape

```mermaid
flowchart LR
    UI["React frontend"] --> API["FastAPI routes"]
    API --> Services["Application services"]
    Worker["Generation worker"] --> Services
    Services --> Managers["Resource managers"]
    Managers --> PrimaryDB["Primary PostgreSQL database"]
    Services --> External["Sleeper and model APIs"]
    Services --> SnapshotBuilder["Snapshot builder"]
    PrimaryDB --> SnapshotBuilder
    SnapshotBuilder --> FrozenDB["Frozen SQLite generation snapshot"]
    FrozenDB --> Reporter["Reporter service"]
    Reporter --> Managers
```

The application remains one codebase and one deployable system. The API and
worker may run as separate processes, but they share services, resource
managers, migrations, and the primary database.

## Repository Structure

```text
backend/
├── __init__.py
├── config.py
├── composition.py
│
├── database/
│   ├── base.py
│   ├── engine.py
│   ├── sessions.py
│   ├── registry.py
│   └── models/
│       ├── core/
│       ├── sleeper/
│       ├── memory/
│       └── reporting/
│
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│
├── resources/
│   ├── context.py
│   ├── competitions/
│   │   ├── objects.py
│   │   └── manager.py
│   ├── sleeper_observations/
│   │   ├── objects.py
│   │   └── manager.py
│   ├── player_catalog/
│   │   ├── objects.py
│   │   └── manager.py
│   ├── league_state/
│   │   ├── objects.py
│   │   ├── manager.py
│   │   └── shared.py
│   ├── data_snapshots/
│   │   ├── objects.py
│   │   └── manager.py
│   ├── memory/
│   │   ├── objects.py
│   │   ├── manager.py
│   │   └── shared.py
│   ├── generations/
│   │   ├── objects.py
│   │   ├── manager.py
│   │   └── shared.py
│   ├── evaluation_workspaces/
│   │   ├── objects.py
│   │   └── manager.py
│   └── audit/
│       ├── objects.py
│       └── manager.py
│
├── services/
│   ├── league/
│   │   ├── identity_service.py
│   │   └── mapping_service.py
│   ├── sleeper/
│   │   ├── client.py
│   │   ├── normalization/
│   │   ├── ingestion_service.py
│   │   └── snapshot_service.py
│   ├── memory/
│   │   ├── memory_service.py
│   │   └── search/
│   ├── generations/
│   │   ├── generation_service.py
│   │   ├── evaluation_service.py
│   │   └── progress.py
│   └── reporter/
│       ├── config.py
│       ├── generator.py
│       ├── runner/
│       ├── tools/
│       ├── prompts/
│       └── procedures/
│
├── api/
│   ├── app.py
│   ├── dependencies/
│   │   ├── context.py
│   │   └── services.py
│   ├── schemas/
│   └── routes/
│       ├── generations.py
│       ├── memory.py
│       └── data.py
│
├── worker/
│   ├── main.py
│   └── dependencies.py
│
└── tests/
    ├── resources/
    ├── services/
    ├── api/
    └── worker/

frontend/
├── package.json
├── src/
│   ├── api/
│   ├── components/
│   ├── features/
│   │   ├── generations/
│   │   ├── memory/
│   │   └── comparisons/
│   └── pages/
└── tests/
```

The `services/` name is intentional. These packages contain more than small
domain modules: the reporter alone contains a runner, tool system, procedures,
prompts, artifact state, and model integration. A service represents a cohesive
application capability and may contain several internal submodules.

## Resource Abstraction

Persistent resources follow four layers:

```text
centralized SQLAlchemy model -> resource object -> manager -> service
```

### SQLAlchemy Models

`database/models/<namespace>/*.py` describes the persistence representation:

- tables and columns;
- relationships and foreign keys;
- uniqueness and consistency constraints;
- indexes and database queryability;
- compatibility with the migration history.

ORM objects are storage types. They must not be returned to routes, workers,
reporter tools, or services.

All ORM models are collected under `database/models/` so the relational graph,
schema ownership, and Alembic target metadata can be inspected in one place.
Namespace subpackages preserve logical ownership without scattering table
definitions across manager packages. ORM modules never import resource objects,
managers, services, or API schemas.

### Resource Objects

`resources/<resource>/objects.py` contains stable caller-facing Python objects.
They represent the resource as the rest of the application understands it and
may include serialization helpers, derived properties, and small object-local
behavior.

Resource objects insulate callers from database-only fields, lazy loading,
session lifetimes, and changes made solely for storage optimization.

API schemas remain separate when an HTTP request or response requires different
validation or presentation. Pure workflow values that are not persisted, such
as a generation manifest or snapshot specification, belong in the relevant service.

### Resource Managers

`resources/<resource>/manager.py` is the safe read and write boundary for the
resource. Managers own:

- SQLAlchemy queries and mutations;
- session lifecycle and short transactions;
- resource and competition scoping;
- mutation provenance and audit context;
- ORM-to-object conversion;
- resource-local consistency rules;
- resource-local query and mutation APIs.

Managers must not perform Sleeper requests, model calls, or long-running work.
They return resource objects rather than ORM rows.

A manager normally owns an aggregate rather than one table. For example, the
generation resource may include its AI calls, tool calls, artifacts, and lifecycle
events. Revision and child rows that have no useful independent lifecycle do
not need separate public managers.

### Shared Transaction Helpers

An optional `shared.py` exists only when a transaction must compose writes
across resource boundaries. These helpers accept an existing session, never
open or commit it, perform no authorization, and are not called by routes,
workers, or services.

For example, finalizing a submitted article and applying its memory mutations
may need one transaction. A generation manager can own that transaction and call
narrow helpers from the generation and memory resources. The service passes a result
bundle, not a database session.

## Service Responsibilities

`services/` contains higher-level application behavior:

- orchestration across multiple managers;
- calls to Sleeper, model providers, and other external clients;
- normalization and merge policy;
- generation and backtest workflows;
- snapshot selection and construction;
- memory lifecycle policy;
- the reporter agent and its internal execution machinery.

Services receive managers and external clients through explicit constructor or
function dependencies. They do not import ORM models, construct raw SQLAlchemy
sessions, or return ORM rows.

Protocols are used for meaningful substitution boundaries, such as Sleeper and
model clients, artifact storage, or clocks. They are not required
for every manager when one concrete implementation and ordinary constructor
injection are sufficient.

`composition.py` contains typed construction functions for services and their
dependencies. It must not become a mutable global service locator.

## API Responsibilities

`api/` is the HTTP boundary. Routes own:

- authentication;
- request parsing and HTTP-specific validation;
- construction of the appropriate manager context;
- dependency wiring;
- translation of results and errors into HTTP responses.

Routes may call a manager directly for a narrow resource read or CRUD operation.
They call a service for multi-resource or external workflows such as starting a
generation, synchronizing Sleeper, or running an experiment.

Routes do not contain business workflows, raw SQL, sessions, model calls, or
data merge logic.

## Authentication, Authorization, and Scope

Authentication belongs at the route or process boundary. Managers do not parse
tokens, cookies, headers, or HTTP sessions.

The responsibilities are split as follows:

| Concern | Owner |
| --- | --- |
| Identify the caller | API authentication dependency |
| Allow invocation of an endpoint | API permission dependency |
| Restrict access to a competition or resource | Resource manager |
| Enforce multi-step workflow policy | Service |

Every manager receives an already-resolved context describing the actor,
resource scope, and relevant correlation identifiers. Initially, actors may be
the local user, a system process, or a generation. Competition-scoped managers
must apply that scope to their reads and writes. Truly global operations, such
as player-catalog ingestion, require an explicit global scope with a reason.

The initial local product does not need enterprise RBAC. The manager context is
still valuable for league isolation, generation provenance, worker attribution,
and a future hosted authorization seam.

Backtest cutoffs, data snapshot IDs, canonical memory revision IDs, and evaluation
workspace artifact IDs are not generic authorization context. They change
generation semantics and therefore remain explicit fields in the generation
manifest and relevant service APIs.

## Worker Responsibilities

The initial worker is a thin process boundary that calls the generation service
and updates generation status/progress. It does not implement database leases,
heartbeats, automatic resume, or a durable scheduler. A stale running generation
is marked failed and can be rerun explicitly.

It does not own generation policy, memory policy, data normalization, or
resource SQL. Like an API route, it constructs an explicit actor and scope at
the process boundary and calls services or managers.

## Database Responsibilities

`database/` contains the complete persistence representation:

- the common SQLAlchemy declarative base;
- constraint and index naming conventions;
- engine construction from configuration;
- read and write session factories;
- common database types when genuinely shared;
- all schema-qualified ORM models grouped by database namespace;
- registration of those models for migrations.

It does not contain caller-facing resource objects, manager/business operations,
a generic CRUD repository, or service workflows.

The backend uses one physical PostgreSQL database because the product's most
valuable audit paths cross its logical domains. A single database makes it
possible to connect an article to its generation, model/token usage, tool evidence, memory
mutations, and factual observations without distributed consistency or service
integration overhead.

Logical ownership remains explicit even though storage is shared. The expected
database domains are:

### League identity

Durable AIdam identities for competitions, ordered seasons, franchises, and
season rosters. This is the minimum bridge that lets a dynasty continue across
Sleeper league IDs. Manager identity, churn history, provider registries, and
reconciliation workflows are deferred.

### Sleeper observations and league facts

Append-only API request/payload history plus a latest normalized view aligned
with the existing datalayer. Raw responses retain hashes and provenance so
request-level refreshes are explainable, idempotent, and usable for historical
snapshot reconstruction.

The player catalog is global and can retain flexible provider metadata while
promoting frequently queried attributes into structured fields. League-specific
lineups, scores, transactions, and roster history remain scoped to a competition
season.

### Reporter memory

Stable storyline, fact, event, trigger, and context identities have complete
versions on one strictly ordered canonical revision history. Introduced/retired
revision bounds select the exact versions visible to a generation. There are no
canonical snapshots, branches, sibling states, merges, or access-history tables.

Each kind owns a distinct typed content contract, including its subjects,
exact-version evidence, stable-item relationships, and event-specific payloads.
A persistent but rebuildable search-document table flattens those different
contracts for entity, relationship, and full-text candidate discovery. Search
results are always hydrated from the canonical typed version before use.

Memory records retain both domain time and observation time, along with the
generation that created the change. A future manual editor can submit a distinct
generation kind instead of introducing a second provenance system.

### Reporting and execution

Durable generations, actual AI-call logs, full tool calls, token usage, and
generic versioned artifacts. Every article is addressed by a generation rather
than a week-based filename.

Reporting also owns one optional active evaluation workspace per competition.
Rolling simulations advance deterministic memory artifacts rather than writing
alternative versions into canonical memory. Discard has no canonical effect;
promotion is allowed only as a fast-forward from the still-current base revision.

Retries and fallbacks are separate AI-call rows so token/model analytics remain
accurate. Dollar costs are calculated from stored tokens and a selected current
or projected price configuration rather than persisted historically.

## Database Construction

The database should be built around the following components before individual
resource schemas are finalized.

### Shared Base and Naming

All centralized ORM models use one SQLAlchemy declarative base and one naming convention
for primary keys, foreign keys, unique constraints, checks, and indexes. This
keeps Alembic output deterministic and makes constraints operable in production.

### Real Constraints

The persistent product database uses explicit primary keys, foreign keys,
essential uniqueness, scope-safe composite keys, concurrency uniqueness, and
sealed-history immutability. Product-semantic ranges, enums, JSON shapes, and
lifecycle policy belong to Pydantic resource objects and manager/service
transactions. The current in-memory assumption that only one league or one
snapshot exists must not carry into the product database.

### Stable Internal Identities

Product-level UUIDs should identify competitions, seasons, franchises,
generations, storylines, canonical memory revisions, data snapshots, evaluation
workspaces, and other durable resources. Sleeper IDs are external identifiers
associated with those resources rather than the product's universal identity
scheme.

### Source Provenance

Ingestion must retain enough information to explain where canonical data came
from and when it was observed. Full provider endpoints can be fetched repeatedly;
payload hashes plus one authoritative normalized head per request scope make
normalization idempotent and safe from out-of-order completion without requiring
a complex incremental API.

### Immutable Revisions and Artifacts

History-sensitive data should be appended as revisions rather than overwritten
without provenance. Articles and any persisted intermediate generation artifacts
are immutable versions associated with a generation.

### Two Time Dimensions

Temporal records that participate in replay should distinguish:

- when an event or state belongs in the fantasy-football domain; and
- when AIdam observed, derived, or created it.

This is sufficient for point-in-time reads without introducing a generic event
store.

### Generation Input Manifest

Every generation row stores typed input snapshot/cutoff columns plus an immutable
JSONB manifest containing its resolved configuration, prompt and procedure
versions, model/fallback policy, tool schema, and code version.

The manifest is the foundation for comparison and reproducibility.

### Short Transaction Ownership

Every public manager operation owns its session. Write methods use short
transactions and finish before returning. Services never hold a database
transaction open during Sleeper requests, model calls, reporter execution, or
filesystem work.

### Full Execution Observability

Model and tool instrumentation is captured at the execution boundary. Each
model-provider attempt, including retries and fallbacks, is recorded separately.
Tool inputs and complete results are retained directly or through immutable
content-addressed artifacts.

### Resource-Safe Read Models

Cross-domain UI projections are exposed through context-aware read-only managers,
not raw SQL called from routes. Generation detail, token/projected-cost dashboards,
article comparisons, and memory audit views may join across logical database
domains while still returning stable resource objects.

## Migrations

`migrations/` owns the single ordered history for the entire primary database.
It imports all centralized ORM models through `database/registry.py` and uses the
shared metadata as its target.

The application must not use `metadata.create_all()` as a production migration
mechanism, and resources must not implement their own runtime schema-version
checks. All structural changes are represented as reviewed migration revisions.

Migration files should be named to communicate their primary resource or
domain, even though they share one sequence. Cross-domain foreign keys and
atomic product workflows are reasons to retain one migration graph rather than
independent migration systems.

Because existing data is ephemeral and reproducible, the new database can begin
with a clean baseline. Migration complexity should optimize for the future
product rather than preserve the existing local SQLite schemas. No migration or
import path from the old context database is required.

## Frozen Run Snapshots

The primary PostgreSQL database contains observations and facts across all
seasons and time periods. Pointing the reporter's guarded SQL tool directly at
that database would create a future-data leakage path.

Before a generation starts, the snapshot service builds or selects a frozen,
cutoff-safe read model containing only the facts visible to that generation. A SQLite
file is a useful implementation because it preserves the existing datalayer
query behavior and physically prevents the reporter from accessing excluded
rows.

Weekly matchup payloads can reconstruct historical game-week roster membership
and starter/bench roles. Transactions and archived observations supplement that
view. Fields that cannot be reconstructed exactly should retain provenance and
an explicit confidence or reconstruction classification.

The snapshot is linked to the generation manifest and may be content-addressed for
reuse. It is read-only and disposable or reproducible; PostgreSQL remains the
source of truth.

## Dependency Rules

Allowed dependencies:

```text
api and worker -> services
api -> resource managers for narrow resource operations
services -> resource managers and resource objects
services -> external-client protocols
resource managers -> database infrastructure
resource managers -> centralized database models and their own objects
database registry -> centralized database models
migrations -> database registry
composition -> concrete services, managers, and clients
```

Forbidden dependencies:

- Routes, workers, or services importing ORM models.
- Routes, workers, or services opening raw SQLAlchemy sessions.
- Managers returning ORM rows.
- Managers making Sleeper or model-provider requests.
- API schemas becoming the internal persistence contract.
- Public generic CRUD repositories that bypass resource policy.
- Arbitrary code resolving dependencies from a global service locator.
- Reporter SQL pointing at the primary product database.
- Cross-domain dashboard SQL bypassing a context-aware manager.
- Transactions remaining open during external or long-running work.

## Testing Strategy

Tests should follow the designed boundary:

- Resource manager tests use real disposable database sessions and explicit
  manager contexts.
- Service tests inject fake managers and fake external clients rather than
  patching internal helpers.
- API tests use dependency overrides and focus on authentication, validation,
  and response translation.
- Worker tests inject fake services and verify generation status/progress behavior.
- Snapshot tests use real SQLite fixtures and verify that future facts are
  physically absent.
- Scope tests prove competition isolation and deliberate global access.
- Transaction tests verify that composed finalization writes commit or roll
  back together.
- Temporal tests verify domain-time and observation-time projections.

## Migration from the Current Codebase

The restructuring should proceed in increments while preserving the working
reporter behavior.

1. Create the `backend/` and `frontend/` roots and shared backend configuration.
2. Establish database infrastructure, PostgreSQL, Alembic, and the clean
   migration baseline.
3. Create the minimal competition/season/franchise/season-roster identity and
   generation resource boundaries.
4. Move the existing reporter into `services/reporter/` without redesigning its
   loop.
5. Route generation through a service and persist AI calls, token usage, full
   tool calls, and generic versioned artifacts.
6. Replace the current context store with linear canonical memory revisions and
   introduced/retired version visibility.
7. Add persistent Sleeper API requests, the normalized current view, and frozen
   data-snapshot construction.
8. Add read-only API routes and the initial generation and memory UI.
9. Add the single evaluation-workspace lifecycle; defer parallel variants,
   generalized scoring, and richer experiment infrastructure until demonstrated.

The existing SQLite context database and output files do not constrain the new
schema. Useful behavior and test fixtures should be preserved; ephemeral data
can be regenerated.

## Key Decisions

- Use a modular monolith rather than microservices.
- Use `backend/` and `frontend/` as the two primary source roots.
- Use `services/` rather than `modules/` for application capabilities.
- Use one PostgreSQL database and one Alembic migration history.
- Centralize all ORM/table definitions under namespace folders in
  `backend/database/models/`.
- Organize persistent boundaries as model, object, manager, and optional shared
  transaction helpers.
- Authenticate at API/process boundaries and enforce resource scope in managers.
- Keep transactions short and owned by managers.
- Store full generation provenance, AI/tool telemetry, versioned artifacts, and
  token usage; calculate prices outside persistence.
- Keep raw Sleeper request history while allowing a simple normalized current
  view.
- Keep canonical memory linear; use introduced/retired revision visibility and
  reporting-owned artifacts for one isolated rolling evaluation.
- Allow only fast-forward workspace promotion—never memory merge or rebase.
- Give every generation an immutable JSONB input manifest and frozen factual
  input.
- Retain SQLite only as a cutoff-safe generation snapshot and testing format, not as
  the primary product store.
