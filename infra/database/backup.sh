#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: backup.sh /absolute/path/to/new-backup.dump" >&2
  exit 2
fi

backup_path=$1
version_backup_path="$backup_path.alembic"
if [[ ${backup_path:0:1} != "/" ]]; then
  echo "backup path must be absolute" >&2
  exit 2
fi
if [[ -e "$backup_path" || -e "$version_backup_path" || \
      -e "$backup_path.sha256" || -e "$version_backup_path.sha256" ]]; then
  echo "refusing to overwrite an existing backup or checksum" >&2
  exit 2
fi
: "${AIDAM_BACKUP_DATABASE_URL:?AIDAM_BACKUP_DATABASE_URL is required}"
: "${AIDAM_DATABASE_CA_FILE:?AIDAM_DATABASE_CA_FILE is required}"
if [[ ! -f "$AIDAM_DATABASE_CA_FILE" ]]; then
  echo "database CA file does not exist" >&2
  exit 2
fi

export PGSSLMODE=verify-full
export PGSSLROOTCERT="$AIDAM_DATABASE_CA_FILE"
export PGDATABASE="$AIDAM_BACKUP_DATABASE_URL"
umask 077
pg_dump \
  --format custom \
  --role aidam_owner \
  --no-owner \
  --no-privileges \
  --schema core \
  --schema sleeper \
  --schema memory \
  --schema reporting \
  --file "$backup_path"
pg_dump \
  --format custom \
  --role aidam_owner \
  --no-owner \
  --no-privileges \
  --table public.alembic_version \
  --file "$version_backup_path"
application_hash=$(shasum -a 256 "$backup_path" | awk '{print $1}')
version_hash=$(shasum -a 256 "$version_backup_path" | awk '{print $1}')
printf '%s\n' "$application_hash" > "$backup_path.sha256"
printf '%s\n' "$version_hash" > "$version_backup_path.sha256"
echo "backup and checksum created; verify private object storage separately"
