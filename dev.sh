#!/usr/bin/env bash

set -Eeuo pipefail

readonly FRONTEND_PORT=3000
readonly BACKEND_PORT=8000
readonly PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

BACKEND_PID=""
FRONTEND_PID=""

log() {
  printf '[dev] %s\n' "$*"
}

is_windows_bash() {
  [[ "${OSTYPE:-}" == cygwin* || "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == win32* ]]
}

windows_port_pids() {
  local port="$1"

  powershell.exe -NoLogo -NoProfile -NonInteractive -Command \
    "Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique" \
    | tr -d '\r' \
    | grep -E '^[0-9]+$' || true
}

unix_port_pids() {
  local port="$1"

  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
    return
  fi

  if command -v fuser >/dev/null 2>&1; then
    fuser "$port/tcp" 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+$' || true
    return
  fi

  log "Cannot inspect port $port: install either lsof or fuser." >&2
  exit 1
}

clear_port() {
  local port="$1"
  local pids

  if is_windows_bash; then
    command -v powershell.exe >/dev/null 2>&1 || {
      log "Cannot inspect port $port: powershell.exe is unavailable." >&2
      exit 1
    }
    pids="$(windows_port_pids "$port")"
    [[ -z "$pids" ]] && return

    log "Stopping process(es) on port $port: $(tr '\n' ' ' <<<"$pids")"
    while IFS= read -r pid; do
      [[ -n "$pid" ]] && taskkill.exe //PID "$pid" //T //F >/dev/null 2>&1 || true
    done <<<"$pids"
    return
  fi

  pids="$(unix_port_pids "$port")"
  [[ -z "$pids" ]] && return

  log "Stopping process(es) on port $port: $(tr '\n' ' ' <<<"$pids")"
  # Ask processes to exit cleanly, then force-stop anything still listening.
  kill $pids 2>/dev/null || true
  for _ in {1..20}; do
    pids="$(unix_port_pids "$port")"
    [[ -z "$pids" ]] && return
    sleep 0.1
  done
  kill -KILL $pids 2>/dev/null || true
}

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM

  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true

  exit "$exit_code"
}

trap cleanup EXIT INT TERM

cd "$PROJECT_ROOT"

command -v uv >/dev/null 2>&1 || {
  log "uv is required but was not found in PATH." >&2
  exit 1
}
command -v pnpm >/dev/null 2>&1 || {
  log "pnpm is required but was not found in PATH." >&2
  exit 1
}
[[ -f .env ]] || {
  log "Missing $PROJECT_ROOT/.env. Create it before starting the app." >&2
  exit 1
}

clear_port "$FRONTEND_PORT"
clear_port "$BACKEND_PORT"

log "Starting backend at http://127.0.0.1:$BACKEND_PORT"
AIDAM_API_PORT="$BACKEND_PORT" uv run --env-file .env aidam-api &
BACKEND_PID=$!

log "Starting frontend at http://127.0.0.1:$FRONTEND_PORT"
pnpm --dir frontend dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort &
FRONTEND_PID=$!

log "Both services started. Press Ctrl+C to stop them."

# Exit if either service fails; the EXIT trap stops the remaining service.
wait -n "$BACKEND_PID" "$FRONTEND_PID"
