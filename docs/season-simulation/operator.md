# Local season campaign operation

The simulator uses ordinary memory-writing generations against a new, uniquely
identified PostgreSQL container. Its database is disposable tmpfs; its prepared
snapshots, source seed and campaign exports live outside Docker under the
worktree's ignored `.context/season-simulation/`. Preparation calls Sleeper only.
The `run` command can call a paid model; preparation, initialization, dry-run,
inspection and export do not generate articles.

## Prepare the first baseline

Run from the committed season-simulation checkout with the project's installed
Python dependencies and Docker Desktop available. Keep this checkout and its
Python environment unchanged for the entire campaign. The controller seals and
checks backend code, prompts, procedure files, dependency versions, settings and
prepared snapshot hashes. It also preserves actual runtime files in exports.
Develop other changes in a separate worktree. A changed runtime fails closed.

The following PowerShell commands propose a concrete 2025 weeks 1–17 baseline.
The league ID is an operator example, never a reference to an existing database.
The cutoff is Tuesday noon UTC after each week's Monday game; actual fetch and
generation observation times stay real. Confirm the league and schedule match
the desired experiment before using this plan. Week 18 can be included with a
separately prepared plan if that league has meaningful week 18 coverage.

```powershell
$env:AIDAM_CODE_VERSION = git rev-parse HEAD
uv run python -m backend.season_simulation.bootstrap prepare `
  --name aidam-season-baseline-2025-01 `
  --output-root .context/season-simulation/baseline-2025-01-target `
  --port 55444 `
  --league-id 1224829459601821697 --season 2025 `
  --first-week 1 --last-week 17 `
  --first-cutoff 2025-09-09T12:00:00+00:00 `
  --model gpt-5.6-luna
```

Port 55444 is a candidate: the command checks that it is free and Docker binds
only `127.0.0.1`. Choose another free port if needed. An existing output directory
or container name is rejected. Container ID, unique label, loopback port and
database addresses are checked before later operations. This workflow does not
use the repository's default Docker Compose project, volumes or existing database.

Preparation executes real Alembic migrations, creates a competition and season,
refreshes source observations through the requested final week, automatically
maps first-season rosters using the normal onboarding service, and prepares one
immutable factual snapshot per week through the normal resolver/materializer.
Missing mappings or unavailable inputs stop preparation visibly. No reporter
memory or generation records are introduced by this operation.

The output contains:

- `target.json`: Docker identity and local paths; no passwords.
- `target.env`: private generated local database credentials. Never commit or
  include this file in shared artifacts.
- `prepared-inputs.json`: exact competition, season, week, cutoff, snapshot IDs,
  hashes, model and request template for campaign initialization.
- `data/`: actual content-addressed snapshot and source payload files.
- `source-only/`: restorable PostgreSQL dump, copied source/snapshot assets,
  prepared input description and SHA-256 manifest, captured before reporter state.

Inspect `prepared-inputs.json` before initializing. Its optional `settings` field
accepts the normal generation settings; for example `{"runner":{"max_turns":60}}`.
Finalize model, fallback, voice, request template and runner limits before `init`.
Do not edit the sealed campaign afterward.

```powershell
uv run python -m backend.season_simulation init `
  --prepared .context/season-simulation/baseline-2025-01-target/prepared-inputs.json `
  --campaign-dir .context/season-simulation/baseline-2025-01
uv run python -m backend.season_simulation dry-run `
  --campaign-dir .context/season-simulation/baseline-2025-01
```

Initialization creates the normal empty canonical root and freezes the campaign.
Dry-run checks the target, code/configuration, chronology, prepared files and
persisted generations without fetching missing inputs or submitting generations.

## Proposed first paid execution

These commands are the paid baseline proposal; implementation tests do not run
them. Load provider credentials into the current process from a private local
source without printing them. The simulator loads its own isolated database
receipt and does not require copying the user's existing database URL.
Implicit `.env` loading by provider libraries is disabled, so load credentials
explicitly before running. Backend/prompt files and the bundled pricing table are
hashed and archived; model/fallback/report/runner settings are sealed in the plan.

```powershell
uv run python -m backend.season_simulation run `
  --campaign-dir .context/season-simulation/baseline-2025-01 --max-steps 1
uv run python -m backend.season_simulation export `
  --campaign-dir .context/season-simulation/baseline-2025-01
```

Inspect the first retained article, brief, tool/model traces and memory revision.
When ready to continue the same frozen campaign:

```powershell
uv run python -m backend.season_simulation run `
  --campaign-dir .context/season-simulation/baseline-2025-01 --max-steps 16
```

The controller is serial. A step observes the preceding successful canonical
head, which can stay unchanged after a legitimate no-op memory closeout. Failure
stops the campaign. Resume reconciles durable generations before deciding whether
to submit; uncertain/running work is not silently submitted again. Token, cost,
time and step limits are checked between generations, not as hard mid-call spend
caps. Step/time limits apply to each invocation; token/cost limits cover cumulative
campaign usage (including failed attempts). Missing usage blocks budgeted runs.
Use `run --help` for exact limits and the explicit `--retry-failed` flag. A retry
also requires increasing `--max-attempts-per-step`; it receives a new stable ID.

```powershell
uv run python -m backend.season_simulation stop `
  --campaign-dir .context/season-simulation/baseline-2025-01
```

Stop requests take effect at a generation boundary. Preserve the target container
while resuming a campaign. Stopping PostgreSQL destroys its tmpfs data, so do not
treat `docker stop` as a campaign pause. The simulator's stop marker is separate.
Use `clear-stop --campaign-dir <campaign>` before resuming after an explicit stop.
When a process dies after committing an article, resume exports that persisted
boundary before submitting another week. Export failure stops further execution.

For an uncertain `running` generation, first verify the original worker process
has ended and inspect its retained generation. After loading only this target's
environment, use the existing explicit recovery command with a timezone-aware
timestamp later than the abandoned generation's last progress:

```powershell
uv run python -m backend.worker.main reconcile-stale `
  --competition-id <competition-id-from-campaign.json> `
  --stale-before <UTC-timestamp> --limit 1
uv run python -m backend.season_simulation run `
  --campaign-dir .context/season-simulation/baseline-2025-01 `
  --max-steps 1 --retry-failed --max-attempts-per-step 2
```

Recovery marks the abandoned attempt failed; it never re-executes a successful
generation. The retry uses a different generation ID and the unchanged prior head.

## Inspect with the existing app

Point a separate local API process at the simulation target, then point the normal
frontend at that API. In a dedicated PowerShell session, load only the target
environment privately:

```powershell
Get-Content .context/season-simulation/baseline-2025-01-target/target.env | ForEach-Object {
  $parts = $_.Split('=', 2)
  [Environment]::SetEnvironmentVariable($parts[0], $parts[1], 'Process')
}
uv run python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 58044
```

In another session, with the frontend's normal dependencies installed:

```powershell
$env:AIDAM_API_PROXY_TARGET = 'http://127.0.0.1:58044'
pnpm --dir frontend dev --port 55144
```

Choose free API/frontend ports as necessary. Open `http://127.0.0.1:55144` and
inspect the simulation competition using existing article/generation/memory
screens. Creating independent UI generations or editing canonical memory while
the controller owns the campaign causes reconciliation to reject unexpected state.

## Export, recover and start comparable campaigns

Run `export` before deleting any target. A successful campaign export contains
the season index, every artifact version, complete database rows for evidence and
model traces, usage, all memory versions, a restorable database dump, actual
external snapshot/payload files and archived runtime assets. A failed export
does not replace the last complete bundle; rerun `export` without regenerating.

For another empty-memory campaign from exactly the same observed sources, restore
the source-only seed to a **new** target; this performs no source fetch:

```powershell
uv run python -m backend.season_simulation.bootstrap restore `
  --source .context/season-simulation/baseline-2025-01-target/source-only `
  --name aidam-season-baseline-2025-02 `
  --output-root .context/season-simulation/baseline-2025-02-target --port 55445
uv run python -m backend.season_simulation init `
  --prepared .context/season-simulation/baseline-2025-02-target/prepared-inputs.json `
  --campaign-dir .context/season-simulation/baseline-2025-02
```

Restore validates the dump and asset hashes and refuses any populated destination.
The fresh target receives its own credentials and receipt, while source identities
and frozen snapshot bytes remain unchanged. Later canonical memories may diverge
because reporter behavior is part of the result.

To recover a complete campaign export for offline/UI inspection after container
loss, use this executable composition. It verifies the bundle, creates a new
target, restores the dump without first creating application schemas, and copies
all external assets:

```powershell
@'
import json
from pathlib import Path
from backend.season_simulation.docker import create_target, restore_database
from backend.season_simulation.bootstrap import export_assets
from backend.season_simulation.export import verify_export
exports = Path('.context/season-simulation/baseline-2025-01/exports')
bundle = exports / json.loads((exports / 'latest.json').read_text())['directory']
verify_export(bundle)
target = create_target(name='aidam-season-inspection-2025-01',
    output_root=Path('.context/season-simulation/inspection-2025-01-target'), port=55446)
restore_database(target, bundle / 'database.dump')
export_assets(bundle / 'data', Path(target.output_root) / 'data')
print(Path(target.output_root) / 'target.json')
'@ | uv run python -
```

Use this new target's API environment for UI inspection. The old campaign receipt does
not silently rebind to a replacement container; source-only restore followed by
new `init` is the supported way to begin another run.

## Historical coverage limits

This is retrospective cutoff reconstruction. It preserves real observation and
execution times while applying the explicit simulated editorial clock to callback
eligibility. Historical roster/current-state attributes, injuries and news are
not reconstructed as if observed that week. Prepared cutoff/coverage warnings
remain part of reporter evidence and exports. The initial bootstrap registers one
season and its normal first-season mappings; it does not invent cross-season
franchise continuity. Scripted smoke completions test mechanics only, and do not
constitute a paid season quality evaluation.

For focused PostgreSQL tests, set only `AIDAM_TEST_DATABASE_URL` from a new owned
test target. Clear `AIDAM_MIGRATION_DATABASE_URL` before invoking pytest: the test
fixtures allocate their own child database and supply its migration URL directly.
Do not source the entire target env into a database test process.
