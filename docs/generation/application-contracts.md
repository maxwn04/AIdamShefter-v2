# Generation Application Contracts

## Contract Layers

| Caller | Contract | Responsibility |
| --- | --- | --- |
| API | generation request/response schemas | authentication, authorization, transport validation, polling |
| Worker/process | `GenerationService` | execute one durable generation and reconcile stale runs |
| Generation service | generation manager | scoped lifecycle, call telemetry, artifacts, and terminal state |
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

## Generation Manager Contract

The generation manager is competition-scoped through `ManagerContext`. Its
public operations are aggregate operations, not generic table CRUD.

Required semantic operations:

```python
class GenerationManager:
    def create_pending(self, command: CreateGeneration) -> Generation: ...
    def start(self, command: StartGeneration) -> Generation: ...
    def update_progress(self, command: UpdateGenerationProgress) -> Generation: ...
    def fail(self, command: FailGeneration) -> Generation: ...
    def cancel(self, command: CancelGeneration) -> Generation: ...
    def get(self, generation_id: UUID) -> GenerationDetail: ...
    def list(self, query: GenerationQuery) -> Page[GenerationSummary]: ...

    def begin_ai_call(self, command: BeginAICall) -> AICall: ...
    def finish_ai_call(self, command: FinishAICall) -> AICall: ...
    def begin_tool_call(self, command: BeginToolCall) -> ToolCall: ...
    def finish_tool_call(self, command: FinishToolCall) -> ToolCall: ...
    def append_artifact_version(
        self, command: AppendArtifactVersion
    ) -> ArtifactVersion: ...
```

Successful finalization requires one additional aggregate operation whose exact
shape depends on the unresolved cross-resource memory transaction decision. It
must at minimum ensure that:

- the generation is still running;
- a final article version exists and belongs to the generation;
- input identity remains unchanged;
- completion timestamps/progress are coherent; and
- a terminal generation cannot be reopened or modified.

### Manager invariants

- Every ID belongs to the manager's competition scope.
- `create_pending` durably captures the original request before external work.
- `start` atomically pins all required inputs and manifest fields.
- input fields are immutable after start.
- AI-call `(turn, attempt)` and tool ordinal identity are manager-controlled.
- a tool call references the successful AI call for its turn.
- full tool result text is retained; structured JSON is additional.
- artifact revisions are positive, append-only, hash-verified, and allocated
  under concurrency control.
- expected lifecycle conflicts raise typed application errors, never leak
  constraint names.

## Reporter Generator Contract

The target generator keeps the current entry point and output shape with narrow
dependency substitutions:

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
) -> ArticleOutput: ...
```

Changes from Reporter V2 are intentionally limited:

- `SleeperLeagueData` becomes an already-open `FrozenLeagueData`;
- legacy `ContextStore` becomes an already-pinned
  `GenerationMemoryContext`;
- durable execution recording is injected;
- filesystem log/output ownership leaves the production generator; and
- legacy memory prepare/finalize calls leave the reporter and move to the
  generation workflow.

The reporter continues to own registry construction, prompt building, brief
seeding, runner construction, and `ArticleOutput` assembly.

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

Reporter V2 currently seeds brief league metadata and resolves roster keys via
private SQLite access. That cannot continue. The new runtime already supplies
league display data through curated snapshot results, but the exact non-tool
metadata contract used to seed `BriefMeta` must be made public or supplied by
`GenerationService`.

Typed memory proposals involving a team require durable `franchise_id` or
`season_roster_id`. The datalayer design promises stable core identity in frozen
snapshots, but the current public `FrozenLeagueData` reporter surface does not
expose a roster-key-to-core-ID resolver. The datalayer owner must define that
read-only adapter seam before team-scoped memory tools can be implemented. The
generation design does not invent its return shape.

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

Exact model-facing memory tool compatibility is intentionally deferred to the
matrix in [`transition.md`](transition.md#memory-tool-compatibility). Tools with
changed meaning need an explicit contract decision before implementation.

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
6. sets local submission state only when `submit_article` returns `ok: true`.

Unknown tools and handler exceptions are durable failed tool calls. Sanitized
error data is persisted, while the model receives the existing safe JSON error
shape. Parallel tool calls use the provider order as `tool_ordinal`; completion
order does not rewrite that order.

All registered tools need an implementation version in durable telemetry. The
manifest hashes the complete ordered model-facing tool definitions, while the
tool-call row records the implementation version used by that handler.

## Artifact Contract

Artifact tools retain their current model-facing signatures. Their internal
context gains a recorder hook that receives complete serialized state after a
successful mutation.

Required mappings:

| Tool event | Durable action |
| --- | --- |
| `write_section`, `rewrite_section`, `set_section_order` success | append complete `article/main` Markdown as `working` |
| `submit_article` success | expose submitted content to generation finalization; do not independently succeed the generation |
| brief mutation | keep in memory; optionally record working brief versions only if later justified |
| generation finalization | append/finalize `article/main`; append final `brief/main` JSON |

Identical consecutive working mutations should not create meaningless versions.
The manager may compare the new content hash and status to the current artifact
version inside its short transaction and return the existing version for a
working no-op. Finalization always appends a distinct `final` version when the
latest identical content is only `working`; artifact versions are never promoted
or mutated in place.

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
- list/read artifact versions and the final article.

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
