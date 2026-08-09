# Database Design Status

## Current Phase

**Phase:** Database-only PR stack implementation  
**Primary database:** Supabase-hosted PostgreSQL  
**Compatibility:** Clean replacement; no legacy data or storage APIs preserved  
**Implementation scope:** Database infrastructure, ORM models, Alembic migrations,
database tests, and operational runbooks only

## Components

| Component | Status | Output |
| --- | --- | --- |
| Platform structure and centralized ORM location | Hardened | `../platform-architecture.md` |
| Cross-namespace contract | Hardened | `overview.md` |
| Minimal core identity | Hardened | `core.md` |
| Request-oriented Sleeper persistence | Hardened | `sleeper.md` |
| Linear canonical memory and isolated evaluation workspace | Hardened | `memory.md` |
| Generation-centered reporting | Hardened | `reporting.md` |
| Supabase/PostgreSQL infrastructure | Hardened | `infrastructure.md` |
| Decision history and user feedback | Current | `log.md` |

## Baseline Scope

- ORM models centralized under `backend/database/models/<namespace>/`.
- Resource objects and managers remain under `backend/resources/`.
- Four core identity tables: competition, season, franchise, season roster.
- Sleeper API requests/payloads plus a current normalized view and frozen data
  snapshots, with one authoritative head per request scope.
- Linear canonical memory revisions with introduced/retired version visibility
  and one current pointer.
- Generations, actual AI-call/token logs, full tool calls, and generic versioned
  artifacts.
- At most one active evaluation workspace per competition, stored through
  reporting artifacts and eligible only for fast-forward promotion.
- Composite competition-scope constraints, immutable factual-snapshot
  membership, and immutable canonical memory revision identity.
- One PostgreSQL database, one migration history, and four private schemas.

## Explicitly Deferred

- manager/person and franchise/name churn history;
- provider registries and cross-provider migration;
- memory snapshots/branches/merges, historical promotion, and Git persistence;
- presets, durable jobs/leases, Pub/Sub, parallel experiment variants, and
  evaluation scoring frameworks;
- pricing catalogs and stored historical cost;
- specialized brief/article schemas and RAG candidate telemetry;
- persistent game/standings projection builds.

These are seams, not placeholder tables. Implementation agents should not
reintroduce them into the baseline without a new decision-log entry.

## Environment Confirmations Before Hosted Migration

These are deployment facts rather than schema blockers:

- Supabase PostgreSQL version, plan, region, connection limits, IPv6
  reachability, backup retention, and PITR availability;
- final retention windows for unreferenced failed API/model payloads;
- whether local PostgreSQL plus a persistent staging project is sufficient or
  Supabase preview branches are worth enabling.

## Next Milestone

Complete, verify, and publish the approved database-only stack with `gh stack`;
do not begin managers or services in this stack.

## Implementation Coordination

This table is the shared ownership ledger for implementation agents. An agent
must stay within its assigned paths and report completion here before another
agent takes over the same scope.

| Stack layer | Owner | State | Assigned paths |
| --- | --- | --- | --- |
| 1. Foundation/private schemas | `foundation_agent` | Complete | `backend/database/` excluding namespace model files; `backend/migrations/` foundation; database test harness; dependency/config files |
| 2. Core identity | `core_agent` | Complete | `backend/database/models/core/`; core migration; core constraint tests |
| 3. Sleeper persistence | `sleeper_agent` | Complete | `backend/database/models/sleeper/`; Sleeper migration; Sleeper constraint tests |
| 4. Memory state | `core_agent` | Complete | `backend/database/models/memory/`; memory migration; memory constraint tests |
| 5. Reporting history | `sleeper_agent` | Complete | `backend/database/models/reporting/`; reporting migration; reporting constraint tests |
| 6. Cross-namespace integrity | `root` | Pending | integration migration; immutability/scope/leakage tests |
| 7. Supabase hardening | `foundation_agent` | Complete | CI and deployment/restore/role/TLS runbooks |

Coordination notes:

- DB-028 is the active validation boundary: namespace implementations must
  remove semantic checks and retain only relational, concurrency, unambiguous
  storage-shape, and sealed-history guarantees.
- Revision IDs are reserved in stack order as `0001` through `0007`.
- Namespace agents do not edit another namespace or reintroduce deferred tables.
- Shared registry and test-harness changes are integrated by `root` after agents
  report their namespace outputs.
- `core_agent`: added the four core ORM tables, revision `0002`, and PostgreSQL
  relational-integrity tests. DB-028 cleanup removed semantic range/nonblank
  checks. Metadata and offline upgrade/downgrade DDL pass; live tests are
  CI-ready.
- `foundation_agent`: added shared Base/types, runtime engine/session/health and
  environment configuration, Alembic environment plus revision `0001`, local
  PostgreSQL role bootstrap/Compose and database CI, and isolated migration,
  session, health, engine, and role-permission tests. Python 3.11 compilation,
  static assertions, Compose validation, and basedpyright pass; live PostgreSQL
  execution remains CI-ready because local execution requires explicit approval.
- `sleeper_agent`: added all 19 request/current/snapshot ORM tables, revision
  `0003`, and DB-028-focused relational/concurrency/storage-shape/immutability
  tests. Live PostgreSQL tests pass and migrated schema matches ORM metadata.
- `sleeper_agent` layer 5: completed the six reporting ORM tables, revision
  `0005`, and DB-028-focused scope, concurrency, provenance, and immutable-history
  tests. The full live PostgreSQL database suite passes (53 tests), reporting
  migration/metadata drift is empty, and offline upgrade/downgrade DDL compiles.
  Layer `0006` must add the deferred artifact/workspace pointer scope rules,
  memory-to-reporting provenance FKs, and cross-namespace final-history guards;
  `root` must also import reporting models into the shared metadata registry.
- `foundation_agent` layer 7: added a role-only hosted bootstrap, manual
  preview/staging verification workflow, mandatory verify-full operator checks,
  credential-free schema reporting, guarded logical backup/restore-drill
  scripts, and deployment/recovery/observability runbooks. Shell/Python syntax,
  Compose validation, static safety assertions, and basedpyright pass; no hosted
  environment was contacted and live hosted gates remain intentionally manual.
- `core_agent` layer 4: hardened the 12-table linear memory model to DB-028,
  added same-competition trigger-target scope, revision/current concurrency and
  sealed-history guards in revision `0004`, and added relational/storage-shape/
  immutability tests. Offline stack upgrade/downgrade passes and live PostgreSQL
  memory tests pass 8/8; reporting provenance remains reserved for `0006`.
