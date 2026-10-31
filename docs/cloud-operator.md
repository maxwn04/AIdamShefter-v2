# Cloud checks and campaign import verification

Use the existing cloud checkout and its Linux-native dependencies. Source the
managed environment's activation script if provided, then use `.venv/bin/python`
explicitly; activation may leave `python` pointing to the system interpreter.
Install missing project dependencies with `uv sync --locked` and
`pnpm --dir frontend install --frozen-lockfile`. The repository pins Python 3.11,
Node 22.22.0 and pnpm 11.19.0. Do not copy Windows virtual environments,
`node_modules`, credentials or private campaign files into the checkout.

## Verify a copied campaign

`scripts/verify_campaign_import.py` is an operator check for the version-1
continuation-subset layout. It checks the copied files and retained history and
reports differences between the frozen Windows runtime and the installed runtime.
It does **not** relocate execution, connect to a database or resume a campaign.

Run from the repository root. Set the two environment variables **before Python
starts** to disable dotenv loading and remote model-price metadata during imports:

```bash
PYTHON_DOTENV_DISABLED=1 LITELLM_LOCAL_MODEL_COST_MAP=True \
  .venv/bin/python -m scripts.verify_campaign_import \
  --import-root /absolute/private-import \
  --manifest-sha256 TRUSTED_TRANSFER_MANIFEST_SHA256
```

Use the manifest digest retained from the independently verified archive. Do not
derive a new digest from altered files after a verification failure. Keep the
input outside Git. The script is read-only and prints a JSON report; if retaining
the report, redirect it to a private location outside Git.

The check covers the complete transfer inventory, safe relative paths, file sizes
and byte hashes, frozen source/pricing, operator/target/preview proofs, prepared
assets, and retained generations/revisions using the existing campaign reconciler.
Windows paths and line endings stay unchanged. No archived script is executed.
The original full-export manifest supplies asset checks only: the subset is not a
complete export or database backup.

`next_week` and `retained_next_status` describe retained evidence, not current live
state or permission to retry. Index receipts show only retained indexing boundaries.
Runtime differences list package versions, Python/pricing differences and changed
configuration **names**, without printing configuration values or narrative text.
Differences are reported, not accepted as compatible. Existing execution/runtime
checks remain unchanged. Live continuation still requires separately reviewed
runtime compatibility and reconciliation of the original target and worker state.

## Offline development checks

```bash
bash scripts/cloud-check.sh
bash scripts/cloud-check.sh --frontend
```

The first command runs focused synthetic import-verification, controller, freeze
and generation tests. It disables dotenv/remote pricing and clears test/migration
database selectors. The frontend option also runs API-schema, formatting, lint,
TypeScript, Vitest and build checks using installed tools; it refuses frontend
dotenv files that Vite might load. Neither command starts a database or application
server, installs dependencies, calls providers, or runs migrations.

Local WSL installation and integration are deferred. These commands use ordinary
Linux tools, but no WSL-specific behavior has been verified.
