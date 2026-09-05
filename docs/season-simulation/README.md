# Season simulation

A campaign is a serial controller over ordinary LIVE generations in a dedicated
local PostgreSQL target. Successful finalization remains the only article and
canonical memory commit boundary. A successful quiet week can retain its input
memory revision. Failed or uncertain generations never cause automatic resubmission.

The controller seals ordered requests, prepared snapshot identities and hashes,
editorial cutoffs, reporter settings, runtime source and installed dependencies.
The bundled pricing table is hashed and archived; usage estimates never depend
on a later remote pricing catalog. Credentials are supplied explicitly, and
simulation commands disable implicit provider dotenv loading.
Every run verifies that seal before submitting work. Prepared execution never
refreshes or builds missing inputs. Execution and observation timestamps remain
real; only callback eligibility uses the explicit simulated editorial time.

See [operator instructions](operator.md) for isolated initialization, preparation,
dry-run, execution, inspection and recovery. Campaign commands are available with
`python -m backend.season_simulation --help`.

## Invariants

- One controller holds a database advisory lock for a competition. Stable UUIDs
  identify the campaign, each step and each explicitly requested retry attempt.
- Reconciliation reads durable generations and canonical revision history; local
  progress is a journal, never evidence of a successful commit. An existing
  running generation stops resume for operator investigation.
- Each successful step consumes exactly the previous successful head. Extra
  generations or unrelated canonical writes invalidate the campaign target.
- A stop file and execution limits apply between generations. They cannot enforce
  a hard budget during an in-flight provider call.
- Export writes a new complete directory and publishes its index last. It
  contains all database tables, artifact versions, complete model/tool payloads,
  canonical memory history, immutable snapshots and source assets. Retrying export
  does not execute a generation. A PostgreSQL dump supports full application restore.

Historical snapshots reconstruct weekly facts from retrospective observations.
They do not recreate historical injury/news/current-state knowledge. Existing
reporter continuity defects remain visible baseline outcomes. There are no memory
branches, promotion, hosted simulation UI or alternate reporter implementation.
