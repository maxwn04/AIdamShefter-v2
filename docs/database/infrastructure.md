# Database Infrastructure Design

**Status:** Hardened design  
**Target:** Supabase-hosted PostgreSQL  
**Schema authority:** SQLAlchemy models plus one Alembic revision history  
**Compatibility:** Clean baseline; no legacy data or schema migration

## Purpose

This document defines how AIdam's four application namespaces are created,
connected to, secured, migrated, tested, observed, and recovered. It deliberately
does not define resource tables; those belong to `core.md`, `sleeper.md`,
`memory.md`, and `reporting.md`.

The infrastructure must support a local-first modular monolith while keeping the
hosted database safe enough to become the durable product source of truth. The
initial system has one trusted backend and one user, but it already contains
valuable long-lived history, exact run provenance, and potentially large source and
artifact payloads.

Supabase provides a real PostgreSQL database, managed backups, poolers, and optional
Data API/Storage services. Those facilities do not change the ownership boundary:
the Python backend owns application persistence and Alembic owns application DDL.

## Settled Recommendations

1. Use PostgreSQL through SQLAlchemy 2.x and Psycopg 3.
2. Use **Alembic as the only application migration authority**. Do not maintain a
   parallel Supabase CLI migration history.
3. Use one linear Alembic history covering `core`, `sleeper`, `memory`, and
   `reporting`.
4. Use a direct Supabase connection for migrations and for long-lived runtime
   processes when IPv6 is available. Use Supavisor **session mode** as the IPv4
   runtime fallback.
5. Do not use Supavisor transaction mode for the initial API or worker.
6. Require TLS with hostname and certificate-chain verification outside local tests.
7. Keep all four application schemas private behind FastAPI. Disable the Supabase
   Data API initially; do not expose these schemas or grant Data API roles access.
8. Use dedicated migrator and runtime roles. Never run the application as
   `postgres`.
9. Schema-qualify every ORM table, foreign key, migration operation, and handwritten
   SQL reference. Do not depend on a broad `search_path`.
10. Use application-generated UUIDv4 primary keys, database-generated UTC
    timestamps, `numeric(12,4)` for exact fantasy scores, JSONB only at deliberate
    extension boundaries, and text statuses validated by application objects.
11. Test models and migrations against real PostgreSQL, not SQLite. SQLite remains
    only the format of the frozen reporter artifact.
12. Keep small and query-worthy payloads in PostgreSQL. Put large immutable binaries,
    especially frozen SQLite artifacts, in a private object store behind
    content-addressed metadata.
13. Treat production migration as a serialized deployment with lock/time limits,
    preflight checks, backup verification, and post-deploy validation.

These recommendations are based on Supabase's current guidance for
[database connection methods](https://supabase.com/docs/guides/database/connecting-to-postgres),
[Data API security](https://supabase.com/docs/guides/api/securing-your-api), and
[hosted-role limitations](https://supabase.com/docs/guides/database/postgres/roles-superuser).

## Target Repository Layout

```text
backend/
├── database/
│   ├── base.py                  # Declarative Base and naming convention
│   ├── types.py                 # Truly shared database types only
│   ├── engine.py                # Runtime engine construction
│   ├── sessions.py              # Session factories and transaction contexts
│   ├── registry.py              # Imports every ORM model for Alembic
│   ├── health.py                # Database readiness/version checks
│   └── models/
│       ├── core/
│       │   ├── competitions.py
│       │   └── franchises.py
│       ├── sleeper/
│       │   ├── requests.py
│       │   ├── league_data.py
│       │   └── snapshots.py
│       ├── memory/
│       │   ├── items.py
│       │   └── revisions.py
│       └── reporting/
│           ├── generations.py
│           ├── artifacts.py
│           └── evaluation_workspaces.py
│
├── migrations/
│   ├── alembic.ini
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── ...                  # One ordered revision graph
│
├── resources/
│   └── */
│       ├── objects.py           # Manager-facing Python/domain objects
│       └── manager.py           # Persistence operations and translation
│
└── tests/
    └── database/
        ├── migrations/
        ├── constraints/
        ├── permissions/
        └── snapshots/

frontend/
```

Operational container/CI files may remain at repository root. There is no
`supabase/migrations/` directory because it would create a second schema history.
If the Supabase CLI is later used for local services or branching, its migration
directory remains empty and CI explicitly invokes Alembic after the database becomes
healthy.

Centralizing ORM models makes the complete relational graph and Alembic metadata
easy to inspect. Namespace subpackages preserve ownership without scattering table
definitions across manager packages. Managers import ORM rows and translate them to
their local resource objects; ORM modules never import managers, services, or API
schemas. Do not replace the manager boundary with a generic CRUD repository.

## One Migration Authority

### Canonical history

Alembic revisions under `backend/migrations/versions/` are the sole executable
history for application schemas, tables, functions, triggers, grants, extensions,
and views. The checked-in SQLAlchemy metadata is the intended current state; Alembic
is the ordered transition mechanism.

The following are prohibited after the baseline begins:

- applying table changes in Supabase Studio's Table Editor or SQL Editor;
- `metadata.create_all()` in application startup;
- maintaining the same DDL in both Alembic and `supabase/migrations`;
- `supabase db push` against application schemas;
- allowing Supabase GitHub integration to deploy a competing SQL history;
- editing an Alembic revision that has reached any shared environment;
- stamping a database without independently verifying its actual schema.

Supabase explicitly warns that remote dashboard edits bypass migration history. Its
CLI normally tracks migrations in `supabase_migrations.schema_migrations`; Alembic
tracks its own `alembic_version`. Using both to own the same objects would make
ordering and drift ambiguous. Supabase supports a
[custom ORM workflow for branches](https://supabase.com/docs/guides/deployment/branching/working-with-branches),
which is the appropriate integration point.

### Alembic configuration

- `env.py` imports `backend.database.registry`, making one complete metadata graph.
- `include_schemas=True`; only `core`, `sleeper`, `memory`, and `reporting` are
  included in autogenerate comparisons.
- The version table is `public.alembic_version`. It is the only AIdam object in
  `public`, has all Data API-role privileges revoked, and avoids a bootstrap cycle in
  which Alembic needs an application schema before its first revision can create it.
- One head is allowed. CI fails on multiple heads rather than silently merging them.
- Constraint and index naming conventions make autogenerated names deterministic.
- Type/default comparisons are enabled; known Supabase-managed schemas and
  extensions are excluded.
- Autogenerate is a draft aid, never an approval mechanism. Every generated revision
  is manually reviewed for data loss, lock behavior, schema qualification, foreign
  key order, and downgrade correctness.
- `alembic current --check-heads` is a runtime/deploy health gate. Alembic documents
  this check in its [official cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html).

### Serialization

Migration deployment acquires a fixed PostgreSQL advisory lock before checking the
current revision and holds it through completion. A second deploy fails or waits for
a short bounded period; two CI jobs never migrate concurrently. Supabase recommends
coordinating one remote migration deployment at a time even for its own migration
workflow.

Do not rely solely on the `alembic_version` row for mutual exclusion: two processes
can read the same head before either advances it.

## Supabase Connection Strategy

Supabase offers direct, Supavisor session, and Supavisor transaction connections.
The direct project hostname is normally IPv6; the shared pooler is the standard IPv4
alternative.

| Use | Preferred connection | Alternative | Prohibited/default-off |
| --- | --- | --- | --- |
| Alembic, `pg_dump`, restore, diagnostics | Direct `db.<ref>.supabase.co:5432` | Supavisor session `:5432` if the runner is IPv4-only and verified compatible | Transaction pooler |
| Persistent FastAPI process | Direct | Supavisor session for IPv4-only host | Transaction pooler initially |
| Persistent worker | Direct | Supavisor session for IPv4-only host | Transaction pooler initially |
| Future serverless/edge process | Transaction pooler `:6543` | Dedicated transaction pooler where available | Direct connection fan-out |
| Local tests | Local PostgreSQL direct | — | Hosted production database |

The supplied `db.ragslfrevzztshyztmzt.supabase.co:5432` value is a direct endpoint.
It is not proof that the executing host has IPv6. Connectivity must be tested during
environment setup without committing credentials.

### Why session mode is the fallback

Session pooling preserves connection-level behavior expected by ordinary SQLAlchemy
and Psycopg clients. It is appropriate for a persistent backend on an IPv4-only
network. SQLAlchemy may use a small local pool in front of it, but total direct and
Supavisor backend connections must remain under the project's compute limit.

### Transaction-mode policy

Transaction pooling is useful when many short-lived serverless instances would
otherwise exhaust connections, but it does not support prepared statements and does
not preserve session state. If later adopted:

- use a separate transaction-pool URL;
- use Psycopg with automatic prepared statements disabled
  (`prepare_threshold=None`), after an integration test against Supavisor;
- prefer SQLAlchemy `NullPool` for ephemeral functions rather than stacking another
  persistent client pool;
- never depend on temporary tables, session advisory locks, `SET` state outside
  `SET LOCAL`, or cross-transaction session affinity;
- never run Alembic through it.

These are environment-specific engine profiles, not conditionals spread through
resource code.

## TLS and Connection Identity

Production, staging, and preview connections use `sslmode=verify-full` and the
Supabase server root certificate downloaded from the project's connection settings.
The certificate is distributed through the deployment secret/file mechanism, not
committed to the repository. Hostname verification matters; `sslmode=require`
encrypts traffic but does not provide the same server-identity guarantee.

Local PostgreSQL may use `sslmode=disable` only on the isolated developer/CI network.
The runtime health check reports TLS use and expected server/database identity without
logging credentials.

Connection URLs must identify their purpose with `application_name`, for example:

```text
aidam-api
aidam-worker
aidam-alembic
aidam-test-<worker>
```

## SQLAlchemy and Psycopg Baseline

Use the synchronous SQLAlchemy 2.x ORM/Core API with Psycopg 3 initially:

```text
postgresql+psycopg://...
```

The current persistence and agent workflows are synchronous, and an async driver
would add session/pool complexity without a demonstrated throughput need. Moving to
SQLAlchemy's async engine later does not change schema or manager contracts.

### Runtime engine profile

Start conservatively and tune from actual concurrency:

- `pool_pre_ping=True`;
- API `pool_size=5`, `max_overflow=5`;
- worker `pool_size=2`, `max_overflow=2`;
- `pool_timeout=10` seconds;
- `pool_recycle=1800` seconds as protection against stale long-lived connections;
- DBAPI connect timeout of 10 seconds;
- default PostgreSQL `READ COMMITTED` isolation;
- connection `application_name`;
- runtime `statement_timeout=30s`, `lock_timeout=5s`, and
  `idle_in_transaction_session_timeout=30s`, set per runtime role or connection.

These numbers are starting limits, not universal constants. The sum of every API and
worker process's pool plus overflow must fit comfortably below the Supabase project's
available server connections, leaving room for Supabase services, migrations, and
administration. SQLAlchemy's official
[pooling documentation](https://docs.sqlalchemy.org/en/20/core/pooling.html) describes
pre-ping and pool bounds.

### Session profile

- one `sessionmaker` per engine;
- `expire_on_commit=False` because managers return detached resource objects;
- `autoflush=False` to keep write points explicit;
- no global/scoped mutable session;
- context-managed session and transaction boundaries;
- rollback and discard a session after an error;
- never hold a session/transaction across Sleeper HTTP calls, model calls, artifact
  uploads, or agent execution.

SQLAlchemy recommends short, explicit session/transaction scopes in its
[session guidance](https://docs.sqlalchemy.org/en/20/orm/session_basics.html).

Read-only work may use `SET TRANSACTION READ ONLY` when useful. Do not create a read
replica or separate read engine until measured load justifies it; replication lag
would complicate run-finalization and audit reads.

## Schema Qualification and `search_path`

Application objects live only in:

```text
core
sleeper
memory
reporting
```

All SQLAlchemy tables specify `schema=...`. Every string foreign key is qualified,
for example `core.competitions.id`. Alembic operations pass `schema=` explicitly.
Handwritten SQL uses qualified relations and functions.

Runtime and migration roles use a restricted `search_path` beginning with
`pg_catalog`; application schemas and `public` are not implicitly searched. This
prevents name-shadowing and accidental creation in the wrong schema. PostgreSQL's
[schema security guidance](https://www.postgresql.org/docs/current/ddl-schemas.html)
warns that adding a schema writable by another user to `search_path` trusts that
user.

The baseline also:

- revokes `CREATE` on schema `public` from `PUBLIC`;
- grants no application role permission to create schemas or tables;
- does not put application helper functions in `public`;
- schema-qualifies extension functions if any extension is later enabled.

## Roles and Least Privilege

Supabase's `postgres` login is privileged but
[is not a true superuser](https://supabase.com/docs/guides/database/postgres/roles-superuser).
Migrations must stay within supported hosted operations and be proven on a Supabase
preview/staging project before production.

### Role layout

Create roles once through a reviewed bootstrap procedure:

- `aidam_owner` — `NOLOGIN`; owns application schemas and objects;
- `aidam_migrator` — `LOGIN`, permitted to `SET ROLE aidam_owner`; used only by
  Alembic CI/manual deployment;
- `aidam_runtime` — `NOLOGIN`; receives explicit schema usage and table/sequence
  DML privileges;
- `aidam_api` and `aidam_worker` — `LOGIN`, members of `aidam_runtime`, with separate
  passwords and connection attribution;
- optional later `aidam_snapshot_reader` — read-only access needed to materialize
  cutoff-safe exports.

`postgres` is reserved for role bootstrap, extension administration, break-glass
diagnostics, and recovery. It is never an application or normal migration URL after
bootstrap.

### Grants

- `aidam_owner` owns all AIdam objects.
- Runtime roles receive `USAGE` on the four schemas and explicit
  `SELECT/INSERT/UPDATE/DELETE` only where the eventual manager contract requires
  them.
- Runtime roles receive no `CREATE`, `TRUNCATE`, `REFERENCES`, trigger-disabling,
  role-management, or extension-management privilege.
- Append-only history tables should omit `UPDATE/DELETE` grants when manager
  workflows can operate with inserts alone; database triggers still enforce sealed
  immutability where required.
- Default privileges are set **for `aidam_owner`**, because default privileges are
  owner-specific. Future Alembic-created objects therefore receive predictable
  runtime grants.
- `PUBLIC`, `anon`, `authenticated`, and `service_role` receive no access to AIdam
  schemas or objects.

Separate API and worker logins allow password rotation and future privilege
separation without changing object ownership. They may share the same baseline
runtime grant role initially.

Supabase physical/daily backups may not retain custom-role passwords; recovery
runbooks must recreate/rotate login secrets after restore.

## Supabase Data API, Auth, and RLS

The initial frontend calls FastAPI. It does not query PostgREST/GraphQL directly.
Therefore:

1. Disable the Data API for the project if no other feature requires it.
2. If it remains enabled, expose none of `core`, `sleeper`, `memory`, or `reporting`.
3. Revoke schema/object/default privileges from `anon`, `authenticated`, and
   `service_role`.
4. Do not place application tables in the exposed `public` schema.

Supabase explains that grants and RLS are separate protections and recommends a
dedicated schema for an intentional API surface. RLS is not enabled on the private
baseline tables because the trusted backend uses direct database roles and manager
scope, not Supabase JWT claims. Adding nominal RLS without a reliable per-request DB
identity would create complexity without a real boundary.

If browser-direct Supabase access is adopted later, create a separate, deliberately
exposed `api` schema containing narrow views/functions. Grant it explicitly, enable
and test RLS on every exposed relation, and audit every `SECURITY DEFINER` function.
Do not expose the storage schemas themselves as a shortcut.

## Shared SQL Conventions

### Identifiers

- Internal primary keys: PostgreSQL `uuid`, application-generated UUIDv4.
- No server UUID default is required. Generating the ID before insert supports
  idempotency keys, graph construction, and deterministic tests.
- Sleeper IDs: `text`, qualified by their concrete resource/scope (for example,
  league plus transaction where Sleeper does not guarantee global identity).
- Human/agent labels are never primary keys.
- UUID ordering has no business meaning; ordering always uses explicit timestamps and
  sequence numbers.

UUIDv7 was considered for index locality, but Python 3.11 has no standard generator
and this workload is far below the scale where random UUID index locality justifies a
project-wide dependency. It can be reconsidered before the baseline is implemented;
mixing UUID versions later is valid but should not be accidental.

### Time

- All instants are `timestamptz` and interpreted as UTC.
- `created_at`, `recorded_at`, and similar knowledge timestamps have
  `server_default=now()` and cannot normally be supplied by untrusted callers.
- Domain dates use `date`; provider epoch values may retain their exact `bigint`
  beside the normalized instant.
- Effective intervals use `[from, through)` semantics with a check that the end is
  after the start.
- Football season/week coordinates remain explicit typed columns; they are not
  inferred from timestamps.
- `updated_at` exists only for genuinely mutable current rows and is changed by the
  owning mutation, not a universal trigger on immutable history.

### Exact numbers

- Fantasy scores: `numeric(12,4)`.
- Token counts and byte sizes: `bigint`, validated as non-negative by application
  objects.
- Durations: `bigint` milliseconds, validated as non-negative by application
  objects, with timestamps retained when endpoints matter.
- Ranks, weeks, rounds, and bounded priorities: `smallint`, with ranges validated
  by application objects.
- Never use PostgreSQL `real`/`double precision` for scored facts that must compare
  exactly. Store provider token counts, not calculated model prices, in the
  baseline reporting schema.

### Status and type values

Use `text` columns with Pydantic enums and workflow validation for bounded
lifecycle/type values. Do not use native PostgreSQL enums or duplicate routine
status policy through database checks. Adding a provider outcome or generation
status is therefore an application change unless it also changes a relational,
concurrency, storage-shape, or sealed-history guarantee.

Free-form classifications and nonblank-text rules are likewise application
validation. Database checks are reserved for shapes whose violation would make a
persisted row ambiguous, not for ordinary user-facing validation.

### JSONB and arrays

- JSONB is for provider long-tail metadata, manifests, diagnostics, structured model
  payloads, and extension attributes.
- Identity, scope, status, time, evidence targets, and common filters remain columns.
- Known top-level JSON shapes are validated by Pydantic; the database checks only
  JSON/location shapes required to distinguish storage representations.
- Canonical hashes use versioned canonical serialization, not PostgreSQL's display
  formatting.
- Add GIN indexes only for real query predicates shown by tests/production plans.
- Arrays are acceptable for compact scalar tags; relational entities and evidence do
  not live in arrays.

### Names, constraints, and deletes

Use one SQLAlchemy metadata naming convention covering `pk`, `fk`, `uq`, `ck`, and
`ix`. Names include table and leading column/semantic label and remain below
PostgreSQL's identifier limit. Every foreign key has an index when it participates in
joins or deletion checks.

Default cross-namespace deletion is `ON DELETE RESTRICT`. Cascades are allowed only
for private child rows whose entire lifecycle is inseparable from a non-audit parent.
Archival, tombstones, or immutable versions handle valuable history.

## Extensions

The baseline requires no optional extension:

- UUIDs are application-generated;
- PostgreSQL full-text search and `tsvector` are built in;
- normalized exact-name lookup uses functional B-tree indexes.

`pg_trgm` may be added for fuzzy name search and `vector` for embeddings only when a
feature and query plan require them. Extension enablement is an Alembic revision,
uses Supabase's supported extension list, specifies the `extensions` schema where
supported, and includes a capability check. It is never a dashboard-only prerequisite.
Supabase documents its available extensions and schema placement in the
[extensions guide](https://supabase.com/docs/guides/database/extensions).

Do not enable `pg_cron`, network extensions, or database-side HTTP merely to replace
the application worker. `pg_stat_statements` is an operational Supabase capability,
not an application-schema dependency.

## Migration Safety

### Baseline construction

Because this is a clean replacement, initial revisions may create complete tables and
ordinary indexes transactionally without compatibility shims or data backfills.
There is no old SQLite import. The baseline is still divided into reviewable revisions
so dependencies and ownership are clear.

Once any shared Supabase environment stores new-format data, revisions are immutable
and forward-only discipline begins.

### Production rules

- Preflight current revision, PostgreSQL version, role, connection mode, free storage,
  active long transactions, and recent backup status.
- Set migration `lock_timeout` to roughly 5 seconds so unexpected contention fails
  rather than freezing the app. Set a per-revision statement timeout appropriate to
  the operation instead of one unlimited global value.
- Inspect the PostgreSQL lock level of every `ALTER TABLE`; many forms take strong
  locks, as documented in PostgreSQL's
  [locking reference](https://www.postgresql.org/docs/17/explicit-locking.html).
- Use expand/backfill/validate/contract revisions after launch: add nullable shape,
  deploy compatible code later, backfill in bounded transactions, validate, then
  tighten/drop in a later release.
- Add expensive check/FK constraints with `NOT VALID`, then `VALIDATE CONSTRAINT`
  where PostgreSQL supports it and live-table impact warrants it.
- Do not combine a long data rewrite with unrelated DDL.
- Backfills use stable key ranges, explicit progress, retry-safe predicates, and
  separate transactions. They are not hidden in ORM startup.
- Destructive drops require a prior release proving no readers/writers remain.

### Concurrent indexes

Use ordinary transactional indexes on an empty/new table. On a populated table where
write blocking is material, use `CREATE INDEX CONCURRENTLY` in a dedicated Alembic
revision and `autocommit_block`. PostgreSQL states that concurrent index creation
cannot run in a transaction and may leave an invalid index on failure. The migration
must detect/clean an invalid same-name index before retry and verify `indisvalid`
afterward. Only one concurrent build per table runs at a time.

`IF NOT EXISTS` is not general idempotency: it can silently accept an incorrectly
defined object with the expected name. Alembic history and explicit catalog
verification are preferred.

### Downgrades

Before initial production adoption, every revision must successfully upgrade an empty
database, downgrade back to base, and upgrade again. This catches dependency-order and
schema-qualification mistakes.

After launch:

- implement a downgrade only when it is operationally safe and lossless;
- for destructive/data-transforming revisions, fail the downgrade explicitly with a
  clear recovery note rather than pretending data can be restored;
- recover production through a forward fix or tested backup/PITR restore, not an
  automatic chain of destructive downgrades.

This is a deliberate distinction between testable DDL reversibility and real data
recovery.

## Local Development and Tests

### Local database

Use a disposable PostgreSQL container whose major version matches the current
Supabase project. Record the detected server version in CI; do not assume hosted
Supabase will remain on one major version forever.

A plain PostgreSQL container is the default because the application does not initially
use Auth, Realtime, or Data API features. Use the Supabase local stack only when a
test genuinely depends on those services. Either way, Alembic—not Supabase SQL
migrations—creates the application schemas.

### Test isolation

- Database tests run against PostgreSQL.
- Each pytest worker receives a uniquely named database (or isolated schema set) and
  applies Alembic from base; no shared mutable test database.
- Constraint/trigger tests attempt invalid SQL directly, not only ORM operations.
- Migration CI tests base -> head, head -> base while prelaunch, and base -> head
  again.
- Autogenerate drift CI constructs head, imports complete metadata, and fails if
  Alembic proposes an unexplained schema diff.
- Permission tests connect as API and worker roles and prove allowed operations work
  while DDL, other schemas, and prohibited mutations fail.
- Snapshot tests use PostgreSQL as source and real SQLite files as output, proving the
  exporter does not rely on PostgreSQL-only query behavior inside the reporter.
- Supabase compatibility tests run on staging/preview for extensions, roles, grants,
  SSL, and hosted restrictions; they never target production.

### Seed and fixture data

Seed only deterministic developer/test identities and compact multi-season scenarios.
Schema statements do not belong in seed files. Large Sleeper payloads remain versioned
test fixtures loaded through test helpers/ingestion paths. Never seed production by
default and never clone production data into preview branches.

Supabase branches are data-less and can run seed files, as described in its
[branching documentation](https://supabase.com/docs/guides/deployment/branching).
When preview branches are adopted, their workflow waits for branch health, obtains
ephemeral credentials, runs `alembic upgrade head`, executes tests/seeds, and discards
the branch. Supabase's automatic migration step must not also own AIdam DDL.

## Secrets and Environment Configuration

Define distinct settings:

```text
AIDAM_DATABASE_URL                 # runtime API/worker URL
AIDAM_MIGRATION_DATABASE_URL       # migrator direct/session URL
AIDAM_DATABASE_CA_FILE             # root certificate path
AIDAM_DATABASE_POOL_SIZE
AIDAM_DATABASE_MAX_OVERFLOW
AIDAM_DATABASE_STATEMENT_TIMEOUT_MS
AIDAM_ARTIFACT_STORE_*             # optional private object-store credentials
```

Rules:

- No password, complete connection URL, service-role key, CA private material, or
  Supabase access token is committed.
- Local `.env` files are gitignored; CI/host secrets are stored in the platform's
  encrypted secret manager.
- Passwords are URL-encoded or passed as structured settings, never concatenated into
  logs.
- Migration credentials are available only to protected deployment jobs/manual
  break-glass operators.
- Runtime and migrator URLs are not interchangeable. Startup refuses the `postgres`
  or migrator role for normal application execution.
- Secret rotation is tested and documented. API and worker credentials rotate
  independently.
- The project reference and host are identifiers, not secrets; database passwords and
  Supabase secret/service keys are secrets.

The connection details supplied for this design contain no password and are not used
or tested during documentation work.

## Payloads, Storage, and Frozen SQLite Artifacts

### Source payloads

Keep content-addressed JSON payloads in PostgreSQL JSONB initially when they are below
a configurable size threshold (recommended starting threshold: 8 MiB). Deduplication
by canonical SHA-256 prevents repeated unchanged player catalogs from multiplying
storage.

Payloads above the threshold may move to a private object bucket. Their relational row
retains hash, byte size, media type, storage key, and observation references. Upload is
staged first; the database locator is committed only after the object hash is verified.
Garbage collection deletes only objects with no retained database reference and after
a grace period.

### Frozen reporter databases

Frozen SQLite snapshots are binary, immutable, content-addressed artifacts, not
PostgreSQL blobs and not a second mutable database. Store small local-development
artifacts on disk; store durable hosted artifacts in a private Supabase Storage bucket
or another object store. The `sleeper.data_snapshots` metadata row retains hash, size,
export schema/materializer version, selected observations, and object locator.

Artifact access is backend-only. The reporter receives a verified local copy opened
read-only. It never receives Supabase database credentials.

Supabase warns that
[database backups do not include Storage object contents](https://supabase.com/docs/guides/platform/backups).
If Storage is used, mirror/version bucket objects independently and run a periodic
integrity job that checks database locators and hashes in both directions. A database
restore without its corresponding object set is not a complete AIdam restore.

## Backups and Recovery

Before new-format data becomes valuable:

- confirm the project's automatic backup tier and retention;
- take an encrypted logical `pg_dump` before risky releases and retain it off-project;
- separately back up private Storage objects;
- document custom-role recreation/password rotation;
- perform a restore drill into a new project, run Alembic head verification, validate
  object hashes, and execute application smoke tests.

Supabase currently documents daily managed backups on paid plans and optional PITR
with finer recovery points. Enable PITR when the accepted recovery-point objective is
shorter than the daily-backup window and durable generation/memory history warrants
its cost. A local hobby phase may accept daily/manual backups, but that acceptance must
be explicit.

Restore is an operational event:

1. stop writers;
2. choose and restore the database point;
3. restore/verify matching object storage;
4. recreate or rotate custom login credentials as required;
5. verify server/extensions, grants, Alembic head, constraints, artifact hashes, and
   representative audit chains;
6. resume workers before API writes only after readiness passes.

Do not treat a successful Supabase dashboard restore as proof that application and
artifact state are consistent.

## Runtime Timeouts, Pooling, and Observability

Capture at minimum:

- checked-out/available/overflow connections and pool wait time per process;
- connection failures and reconnects;
- query duration by normalized operation name, never raw sensitive bind values;
- transaction duration and idle-in-transaction incidents;
- statement, lock, deadlock, serialization, and constraint errors;
- database/storage size growth by namespace/table;
- failed/partial ingestion and artifact-integrity counts;
- current Alembic revision and application code revision;
- migration duration and revision transition;
- slow-query/top-query information from Supabase's observability tools and
  `pg_stat_statements` when accessible.

Alert initially on migration failure, database unreachable, sustained pool exhaustion,
long transactions, repeated lock/statement timeouts, storage nearing plan limits, and
artifact integrity failures. Avoid logging complete model prompts, Sleeper payloads,
credentials, connection URLs, or arbitrary SQL bind values merely for database
observability.

Health endpoints distinguish:

- **liveness:** process is running; no database round trip required;
- **readiness:** bounded `SELECT 1`, expected database/role, TLS in hosted env, and
  Alembic at head;
- **dependency detail:** operator-only diagnostics for server version, connection
  mode, pool, and migration revision.

## Database-Only GitHub PR Stack

After all namespace documents are integrated and approved, implement the database as
a dependency-ordered Graphite/GitHub stack. Each PR contains migrations, matching ORM
models, and database tests; none contains managers, services, API routes, or frontend
work.

1. **Database foundation and private schemas**
   - dependencies, centralized model registry, Base/naming convention, and
     engine/session configuration;
   - Alembic environment, private schemas/roles/grants, local PostgreSQL, and
     migration/permission CI.
2. **Core identity**
   - competitions, ordered seasons, franchises, and season rosters.
3. **Sleeper persistence**
   - refreshes, API requests/payloads, normalized current tables, cutoff-safe
     snapshot manifests, and frozen SQLite export tests.
4. **Memory state**
   - stable items, complete typed versions, entities/relationships, linear
     canonical revisions, and the current-revision pointer.
5. **Reporting history**
   - generations, actual AI-call/token logs, full tool calls, and versioned generic
     artifacts;
   - the single-active evaluation-workspace lifecycle and fast-forward promotion.
6. **Cross-namespace integrity**
   - deferred reporting/memory provenance FKs, revision/workspace input and
     promotion invariants, immutability guards, integrated indexes, and leakage
     tests.
7. **Supabase deployment hardening**
   - hosted role bootstrap/runbook, preview/staging Alembic workflow, SSL verification,
   backup/restore drill, observability and final schema drift report.

Splitting a table and its essential constraints across PRs is avoided unless a
dependency cycle requires a later FK. Every stack level must upgrade an empty database
and pass all tests available at that layer. Production is not touched until the full
stack is reviewed and the staging verification gate passes.

## Verification Gates

### Every schema PR

- one Alembic head and valid revision ancestry;
- upgrade from empty to head;
- prelaunch downgrade to base and re-upgrade;
- no unexplained autogenerate diff;
- model/schema registry imports all tables;
- named constraints/indexes and schema-qualified foreign keys;
- PostgreSQL constraint tests and query-plan checks for critical indexes;
- no credentials or hosted URLs with passwords in diff/logs;
- no `create_all()` runtime path or Supabase migration duplicate.

### Before staging/preview

- direct or session-mode connection verified with `verify-full` TLS;
- migration runs as `aidam_migrator`, not `postgres`;
- app/worker role permission tests pass;
- Data API cannot reach private schemas;
- hosted PostgreSQL version and required extensions match assumptions;
- migration lock/timeouts and concurrent-index behavior tested;
- runtime pool remains below connection budget.

### Before first production migration

- design documents and cross-namespace names are hardened;
- recent backup confirmed and logical/off-project recovery artifact available;
- Storage backup/integrity strategy active if objects are used;
- staging was created from empty and passed end-to-end fixtures;
- restore drill completed;
- exact revision range and lock-risk review approved;
- rollback decision is explicit: safe Alembic downgrade, forward fix, or restore;
- one deployment owner/job and advisory migration lock configured;
- post-migration head, grants, constraints, representative queries, and artifact
  generation verified.

## Rejected Alternatives

### Alembic plus Supabase CLI migrations

Rejected because two histories cannot reliably order the same cross-schema foreign
keys, functions, grants, and table changes. Supabase CLI can operate the local/preview
environment without owning AIdam DDL.

### Dashboard-first schema management

Rejected because it creates drift, weak reviewability, and changes not reproducible
from an empty database.

### Runtime as `postgres` or `service_role`

Rejected because application compromise would gain DDL/broad platform access and
because query provenance/rotation would be weaker.

### Transaction pooling everywhere

Rejected because the initial backend is persistent, session mode is simpler, and
transaction pooling imposes prepared-statement/session-state restrictions without a
current connection-fanout problem.

### Exposing all schemas with RLS immediately

Rejected because the product already has a FastAPI boundary and no Supabase-user
identity contract. It would duplicate manager scope, enlarge the attack surface, and
make every internal table an accidental public API candidate.

### One wide `public` schema and `search_path`

Rejected because it weakens ownership boundaries, risks Data API exposure, and makes
unqualified-name security and migration mistakes more likely.

### SQLite database tests

Rejected because PostgreSQL constraints, schemas, JSONB, locking, concurrent indexes,
roles, and triggers are central to this design. SQLite is tested only as the frozen
reporter artifact format.

### Database UUID generation as the only path

Rejected because application-owned IDs improve idempotent graph creation and retries.
Database constraints, not defaults, remain the source of uniqueness.

### Storing all binaries in PostgreSQL

Rejected for frozen SQLite files and future large artifacts because they do not need
relational querying and can inflate database backup/storage. Small structured payloads
remain in PostgreSQL for cohesion and recovery.

## Integrated Decisions and Environment Confirmations

The schema baseline has settled the design choices:

- application-generated UUIDv4 primary keys;
- `numeric(12,4)` canonical fantasy scores and non-negative bigint token counts;
- centralized ORM models under `backend/database/models/`, with resource objects
  and managers kept together outside the database package;
- separate API and worker logins/application names with the same least-privilege
  grants initially;
- private object storage from the baseline for large source/artifact content,
  with the inline-versus-object threshold kept as deployment configuration;
- retention of the exact frozen SQLite artifact for every factual snapshot
  referenced by a retained generation;
- `public.alembic_version` as the only AIdam object in `public`;
- Sleeper-specific fields in the baseline rather than provider registry tables;
- memory/reporting cross-namespace constraints are added in the integration
  revision, with exactly one resolved memory input per generation, one linear
  canonical current revision, and at most one active evaluation workspace per
  competition;
- evaluation promotion is fast-forward only and never performs a memory merge.

The following are deployment facts to confirm, not unresolved schema design:

1. Supabase plan, PostgreSQL major version, region, connection limits, direct
   IPv6 reachability, backup retention, and PITR availability.
2. The final retention durations for unreferenced failed payloads and diagnostics.
   Referenced source requests, final artifacts, snapshots, and generation manifests
   remain pinned regardless.
3. Whether preview branches are cost-effective at the initial PR volume. Local
   PostgreSQL plus persistent staging is sufficient for correctness; preview
   branches are an optional CI optimization.

None of these confirmations requires connecting to or mutating the supplied
Supabase project during the design phase.
