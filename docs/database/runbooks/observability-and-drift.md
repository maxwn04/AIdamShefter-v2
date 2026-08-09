# Database Observability and Drift

## Readiness and deployment evidence

Liveness does not query PostgreSQL. API/worker readiness uses the bounded
database health check and verifies database name, runtime role, and TLS without
reading the protected `public.alembic_version` table. The migrator deployment
gate separately verifies the expected Alembic head before writers are enabled.
Detailed operator reports may include server version, schema/table sizes,
connection-pool state, and revision, but never URLs, credentials, prompts,
payloads, arbitrary SQL binds, or object-store secrets.

Run the following against protected staging/preview secrets after every schema
change:

```bash
python -m infra.database.verify_database \
  --url-environment AIDAM_MIGRATION_DATABASE_URL \
  --expected-database aidam \
  --expected-role aidam_migrator \
  --profile migrator
alembic -c backend/migrations/alembic.ini current --check-heads
alembic -c backend/migrations/alembic.ini check
python -m infra.database.schema_report \
  --url-environment AIDAM_MIGRATION_DATABASE_URL
```

Repeat `verify_database` with the API and worker URLs and the `runtime` profile.
All commands require the trusted CA and `verify-full`. Review the report for the
expected server version, revision, table counts, size changes, unvalidated
constraints, and invalid indexes. An Alembic diff is a release blocker; never
stamp the database merely to hide drift.

## Initial signals and alerts

Collect pool checked-out/available/overflow counts and wait time by process;
connection/reconnect failures; transaction and normalized-query duration;
statement, lock, deadlock, serialization, and constraint errors; long or idle
transactions; table/storage growth; ingestion failures; artifact-integrity
failures; current code/Alembic revisions; and migration duration.

Alert on database unreachability, migration failure, sustained pool exhaustion,
long transactions, repeated timeouts/deadlocks, storage approaching the plan
limit, and artifact-integrity failure. Use Supabase query insights and
`pg_stat_statements` when available, but do not make that operational extension
an application migration prerequisite.

Review the credential-free schema report with every hosted migration and retain
it with deployment evidence. Any unexpected object, owner, grant, invalid index,
unvalidated constraint, multiple head, or metadata diff stops promotion until a
reviewed Alembic forward fix explains it.
