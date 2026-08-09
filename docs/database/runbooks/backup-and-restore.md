# Backup and Restore Drill

A complete AIdam recovery includes PostgreSQL, private object storage, custom
roles, and rotated login secrets. Supabase database backups do not include
Storage objects.

## Create an off-project logical backup

1. Confirm the managed backup/PITR state and stop or quiesce writers when the
   chosen consistency point requires it.
2. Set `AIDAM_BACKUP_DATABASE_URL` to the migrator's direct or verified
   session-mode connection and `AIDAM_DATABASE_CA_FILE` to the trusted CA. The
   dump sets `aidam_owner` and selects only the four application schemas plus
   `public.alembic_version`.
3. Choose a new absolute path on an encrypted, access-controlled volume:

   ```bash
   infra/database/backup.sh /secure/aidam-2026-08-08.dump
   ```

   The script refuses overwrite, uses `verify-full`, writes separate
   custom-format application and `public.alembic_version` archives without role
   passwords/ownership, applies `umask 077`, and creates both SHA-256 checksums.
   Each checksum file contains only the digest, so a relocated backup is always
   verified against the exact archive path supplied to the restore script.
4. Independently copy/version all referenced private Storage objects. Export an
   inventory containing locator, content hash, and byte length, then verify each
   object against database metadata. Retain the dump, checksum, and object
   inventory together but off-project.

## Restore drill

1. Provision a disposable isolated target named `aidam_restore_*`. Bootstrap its
   roles with `bootstrap_roles.sql`, but do not run Alembic or enable writers.
2. Set `AIDAM_RESTORE_DATABASE_URL`, the CA file, and
   `AIDAM_RESTORE_CONFIRM_DATABASE` to the exact target name.
3. Restore only to the empty drill target:

   ```bash
   infra/database/restore_drill.sh /secure/aidam-2026-08-08.dump
   ```

   The script verifies the checksum, exact target name, safety prefix, and empty
   application schemas before using one `pg_restore` transaction. It never
   cleans or overwrites a populated database.
4. Restore the matching Storage inventory and bytes. Verify locator, hash, size,
   and the absence of both missing and unreferenced retained objects.
5. Run verified database checks for migrator/API/worker roles,
   `alembic current --check-heads`, `alembic check`, and the schema report.
6. Execute representative audit-chain and frozen-SQLite artifact smoke tests.
   Record elapsed restore time and the recovered consistency point.
7. Destroy the disposable target and rotate any drill credentials.

For a real incident, stop writers first. Resume workers and then API writes only
after database, roles, object storage, migration head, and artifact integrity all
pass. A successful dashboard restore alone is not a completed recovery.
