# Offline relocation contracts

Commands run with `PYTHON_DOTENV_DISABLED=1` and `LITELLM_LOCAL_MODEL_COST_MAP=True`; the relocation entry point sets these before loading application modules. It uses local files and installed package metadata only.

- `inspect --import-root PATH --manifest-sha256 SHA`: verify the version-1 subset and summarize the retained boundary.
- `attest --import-root PATH --manifest-sha256 SHA --output PATH`: verify, bind native Linux paths and write a new offline-only record. Prints the record SHA-256 to retain independently.
- `verify --record PATH --record-sha256 SHA`: authenticate the record, repeat evidence verification and require identical paths and observed runtime. No in-place update or force option exists. A new environment needs a new record.

The manifest must explicitly declare `subset=true`, `complete_original_export=false`. Every source/generated file must match size and hash. Duplicate, unsafe, missing, extra and symlink entries fail; relative paths use canonical POSIX spelling. Runtime byte hashes and bundled pricing must match the historical freeze, including CRLF. All retained assets must match the original export asset records, and every prepared/preview snapshot hash must be retained.

The original campaign/progress hash, operator/preview hash and target receipt identity must match. Request IDs remain UUIDv5 of the original campaign and attempt, and the existing reconciler checks exact request/settings/snapshot/memory lineage. Unknown versions, missing evidence tables, duplicate generations/revisions, unrelated competitions, discontinuous revision sequences and invalid generation manifest hashes fail closed. Partial or failed campaign states remain visible and never authorize retries.

The attestation captures Python, complete package inventory, safe configured runtime fields, pricing and archived source hashes plus current adapter source hashes and platform identity. Historical runtime differences are explicit. Even zero differences do not grant execution authorization. `next_step` is zero-based; `next_week` and `retained_next_status` describe retained evidence only, including failed or running work without increasing its attempt count. Tests use synthetic evidence and block network access; no private league fixtures belong in Git.
