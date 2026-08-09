#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: restore_drill.sh /absolute/path/to/backup.dump" >&2
  exit 2
fi

backup_path=$1
version_backup_path="$backup_path.alembic"
if [[ ${backup_path:0:1} != "/" || ! -f "$backup_path" ]]; then
  echo "backup must be an existing absolute path" >&2
  exit 2
fi
if [[ ! -f "$backup_path.sha256" || ! -f "$version_backup_path" || \
      ! -f "$version_backup_path.sha256" ]]; then
  echo "application/Alembic archives and matching checksums are required" >&2
  exit 2
fi
: "${AIDAM_RESTORE_DATABASE_URL:?AIDAM_RESTORE_DATABASE_URL is required}"
: "${AIDAM_RESTORE_CONFIRM_DATABASE:?AIDAM_RESTORE_CONFIRM_DATABASE is required}"
: "${AIDAM_DATABASE_CA_FILE:?AIDAM_DATABASE_CA_FILE is required}"
if [[ ! -f "$AIDAM_DATABASE_CA_FILE" ]]; then
  echo "database CA file does not exist" >&2
  exit 2
fi

export PGSSLMODE=verify-full
export PGSSLROOTCERT="$AIDAM_DATABASE_CA_FILE"
export PGDATABASE="$AIDAM_RESTORE_DATABASE_URL"

verify_checksum() {
  local file_path=$1
  local checksum_path=$2
  local expected_hash
  local extra_content
  local actual_hash

  read -r expected_hash extra_content < "$checksum_path"
  if [[ ! "$expected_hash" =~ ^[0-9a-fA-F]{64}$ || -n "$extra_content" ]]; then
    echo "invalid checksum manifest: $checksum_path" >&2
    exit 2
  fi
  actual_hash=$(shasum -a 256 "$file_path" | awk '{print $1}')
  if [[ "$actual_hash" != "$expected_hash" ]]; then
    echo "checksum mismatch for exact restore input: $file_path" >&2
    exit 2
  fi
}

verify_checksum "$backup_path" "$backup_path.sha256"
verify_checksum "$version_backup_path" "$version_backup_path.sha256"

actual_database=$(psql --no-psqlrc --tuples-only \
  --no-align --command "SELECT pg_catalog.current_database()")
if [[ "$actual_database" != aidam_restore_* ]]; then
  echo "refusing restore outside an aidam_restore_* database" >&2
  exit 2
fi
if [[ "$actual_database" != "$AIDAM_RESTORE_CONFIRM_DATABASE" ]]; then
  echo "restore confirmation does not match target database" >&2
  exit 2
fi

existing_relations=$(psql --no-psqlrc \
  --tuples-only --no-align --command \
  "SELECT count(*) FROM pg_catalog.pg_class AS c JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace WHERE n.nspname IN ('core', 'sleeper', 'memory', 'reporting') AND c.relkind IN ('r', 'm')")
if [[ "$existing_relations" != "0" ]]; then
  echo "restore target is not empty" >&2
  exit 2
fi

pg_restore \
  --exit-on-error \
  --single-transaction \
  --role aidam_owner \
  --no-owner \
  --no-privileges \
  "$version_backup_path"
pg_restore \
  --exit-on-error \
  --single-transaction \
  --role aidam_owner \
  --no-owner \
  --no-privileges \
  "$backup_path"

echo "database restore completed; roles, Alembic head, Storage, and audit chains still require verification"
