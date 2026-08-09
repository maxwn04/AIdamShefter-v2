# Roles and Hosted Deployment

Use this runbook only for a new Supabase preview/staging project or an approved
production release. FastAPI and workers never use `postgres`, `service_role`, or
the migrator login. Alembic remains the only application DDL authority.

## One-time role bootstrap

1. Confirm the project, database name, PostgreSQL version, region, connection
   limit, direct IPv6 or session-pool endpoint, backup tier, and PITR status.
2. Configure `psql` with a protected service/password file. Set
   `PGSSLMODE=verify-full` and `PGSSLROOTCERT` to the project CA. Do not place an
   administrative URL or password in shell history.
3. Connect as the Supabase administrative database role and run:

   ```bash
   psql --no-psqlrc --file infra/database/bootstrap_roles.sql
   ```

4. In the same interactive `psql` session, set fresh secrets without exposing
   them in command arguments, then enable each login:

   ```text
   \password aidam_migrator
   ALTER ROLE aidam_migrator LOGIN;
   \password aidam_api
   ALTER ROLE aidam_api LOGIN;
   \password aidam_worker
   ALTER ROLE aidam_worker LOGIN;
   ```

5. Store the three resulting connection URLs in separate protected secrets.
   Rotate them independently. Re-run the bootstrap file to repair memberships,
   database privileges, timeouts, or restricted search paths; it never creates
   application schemas or tables.

## Preview/staging verification

The manual `Hosted database verification` GitHub workflow accepts only protected
`preview` or `staging` environments. Each environment must define:

- `AIDAM_MIGRATION_DATABASE_URL` for `aidam_migrator`;
- `AIDAM_DATABASE_URL` for `aidam_api`;
- `AIDAM_WORKER_DATABASE_URL` for `aidam_worker`;
- `AIDAM_DATABASE_CA_PEM`, copied from the project's connection settings.

The workflow serializes by environment, requires `verify-full`, upgrades through
Alembic, verifies the single head, roles, private-schema ownership, Data API
isolation, invalid indexes, runtime privileges, and ORM drift, then uploads a
credential-free schema report. It does not seed or clone production data.

## Production release gate

Before adding a production-capable workflow environment, record approval for:

- exact starting and target Alembic revisions;
- recent managed backup plus an encrypted off-project logical backup;
- matching private object-storage backup and integrity inventory;
- successful restore drill and staging verification from an empty database;
- lock review and rollback choice: safe downgrade, forward fix, or restore;
- one migration owner/job and confirmed connection budget headroom.

During the release, stop competing deploys, run `alembic upgrade head` as
`aidam_migrator`, and retain migration output without connection URLs or bind
values. Afterward run `current --check-heads`, all three role verifications,
`alembic check`, and the schema report before enabling writers.

Never use Supabase Studio, `supabase db push`, or a Supabase migration directory
to alter AIdam application objects.
