#!/usr/bin/env bash
# Bounded offline checks using this checkout's Linux environment. No installs.
set -Eeuo pipefail

readonly PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--frontend" ) ]]; then
  printf 'Usage: bash scripts/cloud-check.sh [--frontend]\n' >&2
  exit 2
fi
if [[ ! -x .venv/bin/python ]]; then
  printf 'Missing Linux .venv/bin/python. Run uv sync --locked in this checkout.\n' >&2
  exit 2
fi
.venv/bin/python -c 'import sys; assert sys.platform == "linux", "Use Linux Python"; assert sys.version_info[:2] == (3, 11), "Use the pinned Python 3.11 environment"'

export PYTHON_DOTENV_DISABLED=1
export LITELLM_LOCAL_MODEL_COST_MAP=True
# The offline check command must not inherit permission to create databases.
unset AIDAM_TEST_DATABASE_URL AIDAM_MIGRATION_DATABASE_URL

.venv/bin/python -m pytest \
  tests/scripts/test_verify_campaign_import.py \
  backend/tests/season_simulation/test_controller.py \
  backend/tests/season_simulation/test_freeze.py \
  backend/tests/services/datalayer/test_preseason_snapshot.py \
  backend/tests/services/generations/test_manifest.py \
  backend/tests/services/generations/test_prepared.py

if [[ "${1:-}" == "--frontend" ]]; then
  export COREPACK_ENABLE_NETWORK=0
  # Vite loads frontend dotenv files independently of Python's settings.
  shopt -s nullglob
  for file in frontend/.env*; do
    if [[ "$file" != "frontend/.env.example" ]]; then
      printf 'Frontend dotenv file present; inspect its intended configuration before frontend checks.\n' >&2
      exit 2
    fi
  done
  command -v node >/dev/null
  command -v pnpm >/dev/null
  node -e 'if (process.platform !== "linux" || !process.version.startsWith("v22.22.")) process.exit(2)'
  [[ "$(pnpm --version)" == "11.19.0" ]]
  [[ "$(pnpm --dir frontend exec node --version)" == "$(node --version)" ]]
  export AIDAM_PYTHON="$PROJECT_ROOT/.venv/bin/python"
  for check in api:check format:check lint typecheck test build; do
    pnpm --dir frontend "$check"
  done
fi
