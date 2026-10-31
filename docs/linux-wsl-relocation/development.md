# Cloud Linux development

Work in the existing cloud checkout. Keep imported private evidence outside Git.
Use a Linux-native virtual environment and Node installation; do not copy a
Windows `.venv`, `node_modules`, `.env` or frozen campaign into the checkout.
Local WSL installation and integration are separate from these cloud instructions.

## Dependencies

The repository pins Python 3.11 in `.python-version`, Node 22.22.0 in
`frontend/.node-version`, and pnpm 11.19.0 in `frontend/package.json`. The managed
cloud environment supplies uv and these tools. If it provides an activation
script, source that script in each shell first. Activation need not select the
project Python: use `.venv/bin/python` explicitly for installed project commands.

For an environment that needs its project dependencies installed:

```bash
uv sync --locked
pnpm --dir frontend install --frozen-lockfile
```

These commands install dependencies, not credentials or databases. They require
the normal package registry access. Keep the lockfiles and native dependency
directories separate from historical frozen campaign artifacts.

## Offline checks

```bash
bash scripts/cloud-check.sh
bash scripts/cloud-check.sh --frontend
```

The first command runs the relocation, controller, freeze and prepared-generation
checks using synthetic data. It clears the test/migration database selectors
to prevent accidentally enabling database tests. The frontend option also checks
generated API types, formatting, lint, TypeScript, Vitest and production build.
It refuses frontend dotenv files that Vite could load. Neither command installs
packages, starts servers, calls providers or runs migrations. Python dotenv and
remote model-price loading are disabled for the checks.

## Relocation inspection

Retain the transfer manifest digest from the independently verified private
archive. Do not derive a new trust anchor from files after a verification failure.
Use the actual private import root and trusted digest in place of the placeholders:

```bash
.venv/bin/python -m backend.season_simulation.relocation inspect \
  --import-root /absolute/private-import \
  --manifest-sha256 TRUSTED_TRANSFER_MANIFEST_SHA256

.venv/bin/python -m backend.season_simulation.relocation attest \
  --import-root /absolute/private-import \
  --manifest-sha256 TRUSTED_TRANSFER_MANIFEST_SHA256 \
  --output /absolute/private-reports/relocation.json

.venv/bin/python -m backend.season_simulation.relocation verify \
  --record /absolute/private-reports/relocation.json \
  --record-sha256 SHA256_PRINTED_BY_ATTEST
```

Create the private report directory beforehand. Attestation is exclusive: it will
not overwrite an existing file or write inside the evidence tree. Retain its
printed digest separately. Run verification in the same installed environment;
source, interpreter, kernel, packages or safe runtime-configuration changes
require a new record after inspection. Full records remain private.

`next_week` describes the retained evidence only. A record always says
`execution_authorized: false`; historical runtime differences are reported and
remain unresolved for live continuation. The existing campaign runner is not
connected to this adapter. A later live integration must preserve its target,
runtime and reconciliation checks and independently reconcile the current target
and worker state before any generation or indexing work.
