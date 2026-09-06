# Frozen reporter campaign operations

Use this procedure for selected-week evaluation and sequential seasons. Assessment
and the sample gate live in [evaluation procedure](evaluation-procedure.md).
The [controller](../../backend/season_simulation/__main__.py),
[contracts](../../backend/season_simulation/contracts.py) and
[operator runbook](../season-simulation/operator.md) own executable behavior.
Check their help in the selected implementation checkout; main may lack open-stack
capabilities. Reconcile Git/worktrees/PRs and ignored status/evidence first.

## Isolation and prepared inputs

Keep one operator coordinating paid reporter and embedding execution. Obtain
authorization when absent; reuse authorization already granted within the agreed
scope. An older campaign's approval does not authorize this one. Offline review,
help and targeted scripted tests need no provider calls.

Create a uniquely named Docker target, unused loopback port and new output root
under ignored `.context/`. Never delete/reset an existing DB or campaign for a
clean start. Preserve frozen runtimes, sources, failed targets, attempts and exports.
The receipt checks container ID, unique label, running state and localhost port;
do not bypass it or borrow an active campaign. Stopping the container loses tmpfs
database data: `docker stop` is not a campaign pause.

For new observations, `python -m backend.season_simulation.bootstrap prepare`
accepts `--name`, `--output-root`, `--port`, `--league-id`, `--season`,
`--first-week`, `--last-week`, `--first-cutoff`, `--model`, `--request-template`.
It creates/migrates a fresh target, fetches free Sleeper data, maps rosters and
seals snapshots, retaining a `source-only/` seed. It does not run the reporter.
Use timezone-aware cutoffs after included transaction completion times. The
operator runbook's Tuesday cutoff is an initial example; accepted retained
comparisons used Friday cutoffs. Copy the verified matched plan, not that example.

Two seed formats have different restore paths:

- Bootstrap `source-only/`: use
  `python -m backend.season_simulation.bootstrap restore --source <seed> --name <new-name> --output-root <new-root> --port <unused-port>`.
- Campaign export: this is **not** the bootstrap format. Verify it offline first;
  prove no generations/items/versions and exactly one empty sequence-0 revision.
  Use the runbook's Python composition: `docker.create_target`,
  `docker.restore_database(target, bundle / "database.dump")`, then
  `bootstrap.export_assets(bundle / "data", new_root / "data")`.
  Restore before migrations, since restore refuses populated application schemas.
  Use `bootstrap.migrate_target(target)` on the new target when the candidate
  requires schema additions. Copy only seed campaign `inputs`, update `data_root`
  and `target_file`, select steps, validate with `PreparedInputs`, and write new
  prepared inputs. Never copy campaign identity or progress.

Check new target emptiness again before init. A final season export contains memory
and is for offline inspection in a new target, not empty seeding. Only for changed
snapshot derivations, use the source-only no-fetch rebuild:
`python -m backend.season_simulation.bootstrap rebuild --target <target.json> --prepared <plan.json> --output <new-plan.json> --require-new-snapshots`.
Retain its source-membership audit; omit the last flag only when reuse is intended.
Do not rebuild/refetch unchanged inputs merely for a reporter/retrieval change.

Finalize `PreparedInputs`: competition/season, increasing steps with distinct
snapshot IDs, artifact hashes, input revisions and editorial cutoffs, model,
request template and normal generation settings. Sparse samples have explicit
gaps. After sample acceptance, initialize a separate empty target for the full season.

## Freeze and commands

Use the selected checkout as cwd and a chosen installed Python environment, kept
unchanged for the campaign. Below, `python` means that interpreter (use its absolute
path on Windows). Set `AIDAM_CODE_VERSION` to the reviewed commit; finalize model,
fallback, runner, report and retrieval settings. Set `PYTHON_DOTENV_DISABLED=1`
and `LITELLM_LOCAL_MODEL_COST_MAP=True` consistently before init and later commands.
Load authorized credentials privately; never print `.env` or private database URLs.

[Runtime freeze](../../backend/season_simulation/freeze.py) records backend source,
prompts/procedures, dependency files, installed packages, Python, bundled pricing
and its explicit `CONFIG_NAMES`. It does not seal every environment variable.
Record other relevant configuration explicitly and check it on resume. Changed
sealed inputs require a new candidate, not a manifest edit or check bypass.

Replace placeholders with the intended target paths. These examples do not grant
paid execution authorization:

```text
python -m backend.season_simulation init --prepared <prepared-inputs.json> --campaign-dir <new-campaign-dir>
python -m backend.season_simulation dry-run --campaign-dir <campaign-dir>
python -m backend.season_simulation run --campaign-dir <campaign-dir> --max-steps 1 --max-attempts-per-step 1
python -m backend.season_simulation export --campaign-dir <campaign-dir>
python -m backend.season_simulation verify-export <concrete-export-directory>
python -m backend.season_simulation stop --campaign-dir <campaign-dir>
python -m backend.season_simulation clear-stop --campaign-dir <campaign-dir>
```

Only controller `run` submits reporter/provider work. Init requires a nonexistent
campaign directory under `.context`, source-only state and empty canonical memory;
it freezes inputs/runtime and exports the empty starting boundary. Dry-run checks
all prepared inputs and reconciliation without fetching or generation.

Run one step at a time when reviewing or indexing between weeks. `--max-steps`
and `--max-seconds` bound each invocation at generation boundaries. Optional
`--max-total-tokens` and `--max-cost` cover cumulative campaign generation usage,
including failed attempts; unavailable usage stops a budgeted run. These are
not hard mid-call spend caps, and embeddings need separate accounting.

## Inspect, resume and retain

`progress.json` is a journal; durable generations and canonical revision history
are authoritative. Resolve `exports/latest.json` to an immutable bundle;
`season-index.json` links submitted articles, statuses and memory heads.
Each successful step consumes the preceding successful head; a quiet successful
week may produce no new revision. Reconciliation rejects unrelated writes, extra
generations, wrong inputs and broken lineage. Do not create independent UI reports
or edit canonical memory in a controller-owned target.

Resume the same receipt/runtime/campaign with bounded `run`; it skips committed
weeks and re-exports a committed boundary after process/export failure. Retry
`export` without regeneration. `stop` writes a boundary marker; `clear-stop`
removes it before deliberate continuation. There is no `resume` subcommand.
A lost target cannot be silently rebound to an offline restore.

Failed/cancelled attempts stop by default. When an explicit retry is within scope:
`python -m backend.season_simulation run --campaign-dir <campaign-dir> --max-steps 1 --retry-failed --max-attempts-per-step <increased-total-attempt-limit>`.
Prior attempts remain; the next attempt gets a new deterministic ID. For
`running`/`uncertain`, inspect the original process and generation first. A polling
timeout proves neither failure nor safe retry. Only after confirming an abandoned
worker, use the existing scoped recovery from the operator runbook:
`python -m backend.worker.main reconcile-stale --competition-id <campaign-competition> --stale-before <aware-UTC-timestamp> --limit 1`
with only the owned target environment. Verify the attempt became terminal before
an authorized retry; never recover live work.

Preserve partial/failed exports and the last complete bundle. `verify-export`
checks manifest file hashes offline; also verify submitted versions, per-week
snapshots and memory lineage. Hash integrity proves retention, not good reporting.
Existing app screens may help inspection; no new simulation UI is needed.

## Optional semantic preparation between generations

This section requires the newer implementation candidate; this skills PR does
not add semantic retrieval to main. Read the [semantic composition PR](https://github.com/maxwn04/AIdamShefter-v2/pull/253)
and [index implementation PR](https://github.com/maxwn04/AIdamShefter-v2/pull/251).
In the selected candidate, inspect `docs/reporter-quality/semantic-discovery.md`
and `backend/services/memory/semantic_index/__main__.py`. Confirm it includes
migration, retrieval composition and runtime freeze support before using this section.
Query embeddings are opt-in; generation/search does **not** populate document
embeddings automatically.

Freeze `AIDAM_MEMORY_SEMANTIC_ENABLED`, `AIDAM_MEMORY_EMBEDDING_MODEL`,
`AIDAM_MEMORY_EMBEDDING_DIMENSIONS`, `AIDAM_MEMORY_EMBEDDING_TIMEOUT_SECONDS`.
Defaults are disabled queries, `text-embedding-3-large`, 3072 dimensions and
30 seconds. Preserve matched settings rather than silently enabling semantics.
Ranking/floor are code configuration and freeze with source.

After each successful generation and before the next, read the owned competition's
`memory.memory_search_documents`. The manifest has `competition_id` and `documents`;
each document contains exact `version_id`, complete `document_text`, `content_hash`,
`builder_version`. Include earlier narrative versions for historical discovery.
Retain the input manifest/hashes and canonical head/hash/counts before indexing.

```text
python -m backend.services.memory.semantic_index <manifest.json> --model <frozen-model> --dimensions <frozen-dimensions>
python -m backend.services.memory.semantic_index <manifest.json> --model <frozen-model> --dimensions <frozen-dimensions> --batch-size 64 --execute
```

Set `AIDAM_DATABASE_URL` privately to this disposable target's worker connection.
Preview validates projections with zero provider calls; `--execute` makes
authorized embedding calls and derived writes. CLI timeout is 30 seconds with
no timeout flag. For a different frozen timeout, use `SemanticIndex` with
`OpenAIEmbeddingProvider(EmbeddingSpec(...), timeout_seconds=...)` and the owned
session factory; validate documents before `index_missing`. Compatible rows are
reused; retain failed batches and receipts before retry. Prove canonical memory
unchanged through before/after heads/hashes, then export again to retain derived
rows. Never import a completed season's vectors into a new empty campaign.

Record document and query embedding calls/usage separately: `IndexBuildResult`
reports counts, not a full provider-cost ledger, and generation usage does not
establish embedding spend. Capture authorized usage through the existing provider
boundary or label accounting incomplete; never invent zero cost.

Week 1 starts with no memory to index. Inspect actual `search_memory` semantic
statuses (`ready`, `partial`, `stale`, `unavailable`, `disabled`), coverage and
reasons. Same-run new versions can cause partial coverage. Lexical/structured
fallback is valid degraded behavior; do not claim semantic retrieval was evaluated
when disabled/unavailable/degraded or never invoked. Record useful leads and noise
separately from article and memory outcomes.
