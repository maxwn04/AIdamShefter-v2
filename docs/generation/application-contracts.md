# Generation Application Contracts

## Contract Layers

| Caller | Contract | Responsibility |
| --- | --- | --- |
| API | generation request/response schemas | authentication, authorization, transport validation, polling |
| Worker/process | `GenerationService` | execute one durable generation and reconcile stale runs |
| Generation service | reporting resource managers | scoped lifecycle, call telemetry, artifacts, and terminal state |
| Generation service | datalayer services | optional refresh and ready snapshot resolution |
| Generation service | memory services | revision pin, generation context, and proposal finalization |
| Generation service | reporter generator | produce one article from already-resolved capabilities |
| Reporter tools | `FrozenLeagueData` and `GenerationMemoryContext` | factual reads and pinned-memory reads/buffered proposals |

The examples define semantic boundaries. Exact class and method names may be
adjusted during contract implementation.

## Generation Workflow Values

Workflow values belong under `backend/services/generations/contracts.py`. They
are immutable Pydantic objects, not ORM rows or HTTP schemas.

An initial request needs at least:

```python
class GenerationRequest(BaseModel, frozen=True):
    generation_id: UUID
    competition_id: UUID
    competition_season_id: UUID
    kind: Literal["live", "backtest"]
    request_text: str
    week_start: int | None
    week_end: int | None
    requested_primary_model: str
    settings: GenerationSettings
    rerun_of_generation_id: UUID | None = None
```

The service derives snapshot dates/cutoffs and does not accept a raw snapshot
build key, data artifact path, memory revision selected by an untrusted caller,
or unhashed manifest.

The exact live-versus-backtest mapping to `SnapshotRequest.as_of_date` and
knowledge cutoff is owned by generation policy. It must be specified with
golden tests rather than inferred inside the datalayer.

## Reporting Resource Manager Contracts

The generation manager is competition-scoped through `ManagerContext`. Its
public operations own only generation lifecycle state, not generic table CRUD.

Required semantic operations:

```python
class GenerationManager:
    def create_pending(self, command: CreateGeneration) -> Generation: ...
    def start(self, command: StartGeneration) -> Generation: ...
    def update_progress(self, command: UpdateGenerationProgress) -> Generation: ...
    def fail(self, command: FailGeneration) -> Generation: ...
    def cancel(self, command: CancelGeneration) -> Generation: ...
    def get(self, generation_id: UUID) -> GenerationDetail: ...
    def list(self, query: GenerationQuery) -> GenerationPage: ...
```

Child reporting resources use the same competition scope through independent
manager boundaries:

```python
class AICallManager:
    def begin_ai_call(self, command: BeginAICall) -> AICall: ...
    def finish_ai_call(self, command: FinishAICall) -> AICall: ...
    def get(self, ai_call_id: UUID) -> AICall: ...
    def list(self, query: AICallQuery) -> AICallPage: ...

class ToolCallManager:
    def begin_tool_call(self, command: BeginToolCall) -> ToolCall: ...
    def finish_tool_call(self, command: FinishToolCall) -> ToolCall: ...
    def get(self, tool_call_id: UUID) -> ToolCall: ...
    def list(self, query: ToolCallQuery) -> ToolCallPage: ...

class ArtifactManager:
    def finalize_artifact(self, command: FinalizeArtifact) -> Artifact: ...

class ArtifactVersionManager:
    def append_artifact_version(
        self, command: AppendArtifactVersion
    ) -> ArtifactVersion: ...
```

Successful finalization requires one additional service operation whose exact
shape depends on the unresolved cross-resource memory transaction decision. It
must at minimum ensure that:

- the generation is still running;
- the reporter-selected version exists, belongs to the generation, and is the
  latest revision of its artifact;
- finalization pins that existing version on both the artifact and generation
  without creating a copy;
- input identity remains unchanged;
- completion timestamps/progress are coherent; and
- a terminal generation cannot be reopened or modified.

### Cross-manager invariants

- Every ID belongs to the manager's competition scope.
- `create_pending` durably captures the original request before external work.
- `start` atomically pins all required inputs and manifest fields.
- input fields are immutable after start.
- AI-call `(turn, attempt)` and tool ordinal identity are controlled by their
  resource managers.
- a tool call references the successful AI call for its turn.
- full tool result text is retained; structured JSON is additional.
- artifact revisions are positive, append-only, hash-verified, and allocated
  under concurrency control.
- artifact identity is unique by normalized `(generation_id, path)`, while
  immutable `media_type` describes representation rather than semantic role.
- finalizing an artifact selects its latest existing version and forbids later
  appends.
- a generation's nullable `submitted_artifact_version_id` identifies its exact
  primary output, belongs to a finalized artifact from that same generation,
  and may be set only as the generation succeeds.
- `GenerationQuery(submitted_only=True)` returns only those successful outputs,
  newest completion first, without inspecting artifact paths.
- artifact paths are reporter-owned logical identity only; application queries
  and output roles never depend on a particular path value.
- expected lifecycle conflicts raise typed resource errors, never leak
  constraint names.

AI-call attempts are zero-based within each positive generation turn. Beginning
an attempt locks the competition-scoped parent generation, requires it to be
running, and allocates one more than the greatest existing attempt for that
turn. Tool ordinals are the provider's zero-based request order; beginning a
tool call requires the referenced AI call to belong to the same generation and
to have succeeded. Duplicate ordinals and competing successful attempts surface
as typed concurrency conflicts.

Finishing an already-started AI or tool call does not require the parent
generation to remain running. This lets cancellation or failure race safely
with an in-flight external operation without leaving its durable telemetry open.
No new child call may begin after the parent becomes terminal, and terminal
child rows cannot be finished again.

## Reporter Generator Contract

The target generator keeps the current entry point, adopts `ReporterOutput`,
and makes the required dependency substitutions:

```python
async def generate_article(
    data: FrozenLeagueData,
    config: ReportConfig,
    *,
    memory_context: GenerationMemoryContext | None = None,
    client: CompletionClient | None = None,
    completion: CompletionSettings | None = None,
    runner_config: RunnerConfig | None = None,
    recorder: ReporterExecutionRecorder | None = None,
    complete: CompletionFn | None = None,
    allow_memory_writes: bool = True,
) -> ReporterOutput: ...
```

Changes from Reporter V2 are intentionally limited:

- `SleeperLeagueData` becomes an already-open `FrozenLeagueData`;
- legacy `ContextStore` becomes an already-pinned
  `GenerationMemoryContext`;
- durable execution recording is injected;
- structured brief/article state becomes path-addressed Markdown artifacts;
- filesystem log/output ownership leaves the production generator; and
- legacy memory prepare/finalize calls leave the reporter and move to the
  generation workflow.

The reporter continues to own registry construction, prompt building,
`research/brief.md` seeding, runner construction, and `ReporterOutput` assembly.

The output selects the submitted artifact and returns one complete current
snapshot for every artifact in deterministic path order:

```python
class ArtifactSnapshot(BaseModel, frozen=True):
    path: str
    media_type: Literal["text/markdown"]
    content: str
    revision: int
    content_hash: str


class ReporterOutput(BaseModel, frozen=True):
    submitted_path: str | None
    artifacts: tuple[ArtifactSnapshot, ...]
```

`ReporterOutput` can represent an unsubmitted diagnostic result, but generation
success requires one non-null `submitted_path`. The snapshot matching that path
is the exact revision selected by `submit_artifact`; the service does not infer
a later revision or classify the output from its name. `content_hash` is
lowercase SHA-256 over the exact UTF-8 content.

The production path always supplies a durable recorder. Tests may use an
in-memory recorder, and a transitional standalone CLI may omit it.

## Frozen Datalayer Adapter

The reporter-owned datalayer adapter recreates the 18 tool definitions and
handlers in the new backend reporter package. The now-closed reporter-adapter PR
is useful compatibility evidence, but it is not part of `main` and is not a
required parent. The new adapter receives one `FrozenLeagueData` and delegates
directly.

The generation service owns:

```python
snapshot = snapshot_service.get_or_create(snapshot_request)
with FrozenLeagueData.open(snapshot) as data:
    output = await generate_article(data, ...)
```

The reporter does not receive `DatalayerSnapshotService`, a PostgreSQL
connection, a source client, or the snapshot artifact path separately.

### Required metadata/identity seam

Reporter V2 currently seeds structured brief league metadata and resolves
roster keys via private SQLite access. That cannot continue. The new runtime
already supplies league display data through curated snapshot results, but the
exact non-tool metadata contract used to seed `research/brief.md` must be made
public or supplied by `GenerationService`.

Typed memory proposals involving a team require durable `franchise_id` or
`season_roster_id`. Snapshot projection v2 stores one exact core identity for
every selected Sleeper roster and `FrozenLeagueData` exposes the typed,
read-only resolution seam:

```python
class FrozenRosterIdentity(BaseModel, frozen=True):
    competition_id: UUID
    competition_season_id: UUID
    season_roster_id: UUID
    franchise_id: UUID
    sleeper_roster_id: str
    team_name: str | None
    manager_name: str | None


RosterIdentityResolution = (
    ResolvedRosterIdentity
    | AmbiguousRosterIdentity
    | RosterIdentityNotFound
)


def resolve_roster_identity(
    roster_key: str | int,
) -> RosterIdentityResolution: ...
```

Positive Sleeper roster IDs resolve exactly. Other keys use an exact,
case-insensitive team-name or manager-name match. Ambiguity and absence are
typed results rather than exceptions. Resolution reads only the already-open
immutable snapshot; reporter memory tools never query PostgreSQL for identity.

## Typed Memory Adapter

The reporter memory adapter receives exactly one `GenerationMemoryContext`.
It may:

- call `context.search()` at the pinned revision;
- call typed `propose_*` and `replace_*` methods;
- return proposal-local references for relationships within the run; and
- translate typed validation errors into safe tool results.

It may not:

- import memory managers or ORM models;
- select or advance canonical revisions;
- commit a proposal immediately;
- expose buffered proposals as retrieved canonical memory;
- infer core entity IDs from display names without an authoritative resolver;
  or
- dual-write legacy `ContextStore` and typed memory.

`GenerationService` calls `take_completed_bundle()` once after reporter success
and decides whether to apply or discard it. The reporter tool adapter never
calls `MemoryMutationService.apply()`.

The model-facing memory tool mapping is recorded in the matrix in
[`transition.md`](transition.md#memory-tool-compatibility). Generation 8b
settles that contract as `search_memory` plus explicit per-kind `propose_*`
and `replace_*` operations. Search returns hydrated canonical matches and
optional exact/stable expansions, so there is no candidate-fetch tool.

Team-facing arguments use frozen roster keys. The adapter resolves franchise or
season-roster UUIDs according to the canonical field being populated and fails
closed on ambiguous or absent identities. Proposal-local IDs may be used by
later proposals as relationship targets, but may not themselves be replaced in
the same bundle.

Facts and events are limited to `unverified` or `inferred` confidence until a
separate model-addressable durable receipt contract exists. The proposal tool's
own call ID is recorded as creation provenance, never misrepresented as the
primary factual receipt.

## Model Completion and AI-Call Contract

The existing `CompletionClient` remains the retry/fallback owner. It receives a
generation-scoped recorder plus the runner's turn number without passing
platform-only values to the provider.

For each provider attempt:

1. Allocate/start an AI-call record immediately before invoking the transport.
2. On success, normalize provider/model/finish/usage metadata, persist the exact
   sanitized response, and finish the AI-call record.
3. On a retryable error, finish the record as `retryable_error`, then apply the
   existing delay/fallback policy.
4. On a non-retryable error, finish the record as `fatal_error` and re-raise.
5. On cancellation, mark the in-flight attempt cancelled when outcome is known;
   use `unknown_outcome` only when the provider outcome truly cannot be known.

Token normalization maps only values present in the provider response:

```python
class TokenUsage(BaseModel, frozen=True):
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    raw_provider_usage: dict[str, Any] | None = None
```

The normalization helper is provider-response-facing and golden-tested. It does
not estimate missing values, calculate price, or silently fold cached/reasoning
tokens into another category.

The successful AI-call identity must be available to tool-call recording. The
implementation may return a small internal completion envelope or let the
recorder resolve the unique successful call for `(generation_id, turn)`. This
is an implementation choice, but raw persistence IDs must not enter model
messages or tool schemas.

## Tool Execution Contract

`Runner` remains the dispatch owner. For every model-requested call it:

1. creates the durable tool-call row before handler invocation;
2. executes the existing handler, including parallel batches;
3. captures full string output plus structured JSON when valid;
4. records duration and success/failure;
5. returns the same tool-result content to the model; and
6. sets local submission state only when `submit_artifact` returns `ok: true`.

Unknown tools and handler exceptions are durable failed tool calls. Sanitized
error data is persisted, while the model receives the existing safe JSON error
shape. Parallel tool calls use the provider order as `tool_ordinal`; completion
order does not rewrite that order.

All registered tools need an implementation version in durable telemetry. The
manifest hashes the complete ordered model-facing tool definitions, while the
tool-call row records the implementation version used by that handler.

## Artifact Contract

The reporter replaces section-specific brief/article tools with one generic,
path-addressed Markdown contract:

```python
list_artifacts()
read_artifact(path)
create_artifact(path, content)
edit_artifact(path, old_text, new_text, expected_revision)
submit_artifact(path, expected_revision)
```

Artifacts use `text/markdown`. Paths are normalized relative logical names, not
host filesystem paths. The reporter may use defaults such as
`research/brief.md` and `article.md`, but owns those names and may select another
publishable path. `create_artifact` rejects an existing path.
`edit_artifact` succeeds only when `expected_revision` is current and
`old_text` occurs exactly once; zero or multiple matches are typed tool errors.
It performs one literal replacement and appends the resulting complete content
as a new immutable version. There is deliberately no `replace_all` mode.

`list_artifacts` and `read_artifact` never append versions. Failed mutations and
content-identical edits do not append versions. Each successful create/edit
passes its complete snapshot to the recorder with source AI/tool provenance.
The generator records its seeded `research/brief.md` snapshot as revision 1
before the first model call, with no source AI call or tool call.

`submit_artifact` accepts any non-empty artifact, requires its expected current
revision, records no content version, and ends the reporter loop. The resulting
`ReporterOutput` contains `submitted_path` plus current snapshots of all
artifacts. Generation finalization finalizes that artifact and sets
`generation.submitted_artifact_version_id` to the same existing version. It
never appends a distinct final copy or mutates an artifact version in place.

The reporting resource layer exposes this as
`GenerationQuery(submitted_only=True)`. That query is the current article
history read model: it is competition-scoped, orders by `completed_at DESC, id
DESC`, and can fetch each exact article through the returned submitted version
ID. A future user-facing API may aggregate competitions authorized for one
user, but must preserve this explicit pointer contract rather than classify
artifacts by path.

## Manifest Contract

Before running, the generation manifest must include or hash-reference:

- generation kind and resolved request settings;
- data snapshot identity, projection version, and sealed artifact hash;
- pinned canonical memory revision or evaluation artifact identity;
- domain and knowledge cutoffs;
- requested model, fallback chain, retry policy, and runner settings;
- system prompt and procedure content hashes;
- ordered tool-schema bundle hash and tool implementation versions;
- reporter/generation code revision; and
- manifest schema version.

Canonical JSON and hashing behavior must have golden vectors. The manifest does
not duplicate full SQLite request membership already sealed under the referenced
data snapshot.

## Generation Service Contract

The service surface should distinguish submission from execution even if the
initial API performs both in one process:

```python
class GenerationService:
    def submit(self, request: GenerationRequest) -> Generation: ...
    async def execute(self, generation_id: UUID) -> GenerationResult: ...
    def reconcile_stale(self, policy: StaleGenerationPolicy) -> ReconcileResult: ...
```

This keeps a clean queue seam without introducing job/lease infrastructure.
`execute` is idempotent only in the narrow sense that it refuses a generation
that is not eligible to start; it does not resume or replay a partially executed
agent loop. An explicit rerun creates another generation.

## API Boundary

The initial API remains polling-oriented:

- submit a generation;
- get generation status/progress;
- list competition generation history;
- read generation detail and exact manifest;
- list/read AI calls and token usage;
- list/read tool calls and full results; and
- list/read artifact versions and the generation's submitted output version.

Routes authenticate/authorize, build context, call manager reads or
`GenerationService`, and translate typed errors. They do not run model loops,
open sessions, access artifact paths, or calculate generation policy.

Endpoint paths and synchronous-versus-background submission behavior remain an
API implementation decision. The database baseline requires polling but does
not require SSE or a durable queue.

## User Attribution Gap

Current contracts support only an anonymous `LocalUserActor` kind. There is no
durable product-user resource, competition membership, or generation owner.
Sleeper users cannot fill this role because core explicitly treats them as
observed fantasy-league data rather than authenticated people.

Before claiming per-user tracking, decide:

- whether the first platform remains single-local-user or becomes multi-user;
- the authoritative product-user identity source;
- how competition access/membership is represented; and
- whether generations store requester ID, actor snapshot, or both.

Until that decision, the implementation may preserve local-user provenance in
`ManagerContext` but must not document or expose durable per-user generation
history.
