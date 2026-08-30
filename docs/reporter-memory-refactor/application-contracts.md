
# Reporter Memory Recall and Closeout Refactor Application Contracts

## Vocabulary and Ownership

- **Result:** the logical tool value returned to the reporter. The tool owns its shape.
- **Result text:** the exact serialized string placed in the model conversation for a tool result.
- **Metadata:** application-only identity, provenance, ranking, binding, and diagnostic data for a tool execution. It is never returned to the reporter.
- **Presentation:** a bounded transformation from canonical memory records into a semantic result plus metadata.
- **Recall prelude:** application-selected semantic memory supplied when a memory-enabled generation starts.
- **Memory closeout:** the mandatory post-submit procedure performed by the same reporter agent before the runner terminates.

## Public Contracts

### Internal tool execution result

Handlers that need application-only metadata return:

```python
@dataclass(frozen=True)
class ToolExecutionResult:
    result: JsonValue | str
    metadata: dict[str, JsonValue] = field(default_factory=dict)
```

The wrapper is runner infrastructure and is never serialized wholesale. The runner performs the equivalent of:

```python
execution_result = handler(**arguments)
model_message = serialize(execution_result.result)

saved_tool_call.result = execution_result.result
saved_tool_call.result_text = model_message
saved_tool_call.metadata = execution_result.metadata
```

Existing tools may continue returning a plain JSON-compatible value or string. The runner normalizes that value to `ToolExecutionResult(result=value, metadata={})`.

### Saved `ToolCall`

The saved resource and reporting API expose these stable fields:

```json
{
  "id": "7b36911d-8bd4-4a99-b18a-a25a1808096a",
  "generation_id": "284a799a-d313-442f-b961-017508ac162e",
  "turn_number": 6,
  "tool_ordinal": 0,
  "tool_name": "search_memory",
  "implementation_version": "semantic-memory-v1",
  "arguments": {
    "text": "Waffle House scoring decline",
    "kinds": ["storyline", "trigger"],
    "limit": 5
  },
  "result": {
    "memories": [
      {
        "kind": "storyline",
        "headline": "Waffle House keeps escaping disaster",
        "summary": "Three narrow wins have hidden a declining scoring trend.",
        "status": "active",
        "subjects": ["Waffle House"],
        "callback_condition": "Revisit after their next loss."
      }
    ],
    "truncated": false
  },
  "result_text": "{\"memories\":[...],\"truncated\":false}",
  "metadata": {
    "pinned_memory_revision": 18,
    "candidate_count": 14,
    "bindings": [
      {
        "result_ordinal": 0,
        "item_id": "f93e441b-4ea4-4c14-a26f-c8c676af3c47",
        "version_id": "dca2901d-7990-4dad-b173-d75605ba382a",
        "item_revision": 6,
        "retrieval_score": 0.84721
      }
    ]
  },
  "status": "succeeded",
  "duration_ms": 42,
  "error": null
}
```

The contract is:

- `result` is exactly the logical value returned to the reporter.
- `result_text` is exactly the serialized string placed in the model conversation. It also supports Markdown and plain-string tool results.
- `metadata` is never returned to the reporter.
- `tool_name`, `implementation_version`, `arguments`, `result`, `result_text`, `status`, `duration_ms`, and `error` remain first-class fields shared by all tools.
- Tool-specific private values belong under `metadata`; no separate per-key metadata fields are introduced.

Repository implementations may map structured fields to JSONB columns, but domain and API names remain `arguments`, `result`, and `metadata`.

### Model-facing memory search

The writer-facing search accepts only editorial selectors:

```python
class MemorySearchArgs(BaseModel):
    text: str | None = None
    team_keys: list[str] = []
    tags: list[str] = []
    kinds: list[MemoryKind] = []
    statuses: list[str] = []
    week_from: int | None = None
    week_to: int | None = None
    limit: int = 8
    include_evidence: bool = True
    include_related: bool = True
```

Canonical item IDs, version IDs, entity IDs, related-item IDs, evidence-version IDs, and expected revisions are not model-facing search inputs. Temporal bounds are inclusive. Server-side league and season scope is mandatory and implicit.

The logical tool `result` has the semantic shape:

```python
class MemorySearchContext(BaseModel):
    memories: list[MemoryContext]
    notice: str | None = None
    truncated: bool = False
```

Each memory kind exposes only fields useful to writing:

- **Storyline:** headline, summary, status, salience, arc type, human-readable subjects, tags, callback condition, bounded semantic evidence, related-memory summaries, and relevant week.
- **Fact:** claim, category, important numbers, confidence, status, human-readable subjects, and relevant week.
- **Event:** event type, headline, summary, salience, confidence, status, human-readable participants/assets, and relevant week.
- **Trigger:** trigger type, status, fire policy, condition summary, due week or due time, and linked-memory summaries.
- **Context note:** scope label, narrative, outlook, status, and tags.

No model-facing result contains canonical IDs, version IDs, revisions, creation/recording timestamps, competition IDs, content hashes, rank scores, matched keys, raw rank components, or projection details.

The paired `metadata` may contain:

- presentation schema and builder versions
- pinned memory revision and resolved scope/query
- candidate, returned, omitted, and truncation counts
- canonical bindings by stable result ordinal
- item/version IDs, agent keys, expected revisions, matched keys and reasons, rank components, and omitted-field diagnostics

### Recall prelude

Generation-start recall consumes generation scope, request intent, snapshot week, and pinned memory revision. The reporter receives only semantic context grouped into due callbacks, standing context, and likely relevant memories. Canonical bindings and selection diagnostics remain metadata.

Trigger evaluation is deterministic. A trigger is due according to its stored fire policy and current generation scope, not because the writer happened to search for or interpret it.

### Memory closeout procedure

After successful `submit_artifact`, its result includes the `memory_closeout` procedure as the mandatory next action. The same tool-result message remains valid conversation history; the runner does not synthesize a tool call or change the available tool definitions.

The procedure requires the reporter to:

- review the finalized article and verified research brief;
- identify only information likely to improve future reporting;
- search existing memory when useful to avoid duplicate or contradictory entries;
- create or update appropriate facts, events, storylines, triggers, and context notes using existing semantic memory tools;
- avoid saving article prose, style instructions, unsupported inference, or routine transient details without future narrative value;
- save nothing when no durable memory is warranted;
- finish by calling `complete_memory_review`.

`complete_memory_review` has no required model-supplied bookkeeping fields. The application derives proposal counts and outcomes from recorded calls and the generation memory context.

## Lifecycle and State Transitions

The runner tracks two lifecycle facts:

- `article_submitted`
- `memory_review_completed`

A memory-enabled run begins with both false. A successful `submit_artifact` sets `article_submitted`, freezes the selected artifact revision, activates the closeout procedure in the returned result, and keeps the loop running. A successful `complete_memory_review` requires `article_submitted`, sets `memory_review_completed`, and terminates the loop.

The runner terminates normally only when both facts are true. The tool definitions and their ordering remain constant on every completion request. Six additional closeout turns guarantee the reporter receives an opportunity to act even when submission occurs at the normal writing-turn limit; the submission turn does not consume this allowance.

Live finalization consumes the existing generation memory proposal bundle. Backtest mode continues returning blocked results for memory writes and completes closeout as a no-op.

## Invariants

- `result` is the logical value returned to the reporter, and `result_text` is the exact serialized tool message placed in its conversation.
- `metadata` never enters the model conversation unless a tool deliberately promotes a value into its public `result` contract.
- Every presented canonical memory that may later be updated has a hidden, unambiguous binding in metadata.
- All memory reads and writes remain league-and-season scoped.
- A model cannot select a canonical record by supplying an identifier hidden from its context.
- Due triggers and applicable context notes do not depend on an optional writer search.
- Submission makes the selected artifact immutable before closeout begins.
- Tool availability does not change during a run.
- Memory closeout permits zero writes and still requires explicit completion.
- Live generation produces zero or one canonical memory revision through the existing finalization path.
- Backtest and simulation runs do not produce canonical memory proposals.

## Error Semantics

- Invalid model-facing search arguments return a bounded tool error without storage details.
- Presentation or serialization failure fails the tool call and records diagnostics in metadata and error fields.
- `complete_memory_review` before successful submission returns a bounded lifecycle error and does not terminate the runner.
- Attempts to edit the submitted article retain the existing `artifact_finalized` error.
- Reaching six closeout turns without completion is recorded distinctly, fails reporter execution, and causes generation failure to discard the proposal buffer.
- Invalid memory proposals retain existing tool and generation-finalization error behavior.

## Compatibility and Transition

1. Add `ToolExecutionResult` support while treating existing raw handler returns as `result` with empty metadata.
2. Add the `result`, `result_text`, and `metadata` reporting fields. Map existing structured results to `result`, exact result strings to `result_text`, and initialize missing metadata to an empty object.
3. Migrate memory search to semantic presentation and hidden bindings; preserve canonical store search APIs for trusted callers.
4. Add the automatic recall prelude and deterministic trigger evaluation.
5. Add the forced same-agent memory-closeout procedure and `complete_memory_review` terminal tool while keeping the tool schema stable.
6. Retire the structured-brief fact bridge. Brief facts remain article working state, and only explicit reporter-selected proposals enter generation memory finalization.

No compatibility layer should duplicate canonical writes. Reporting rows without metadata remain readable with an empty object.

## Acceptance Coverage

- Runner tests prove metadata never appears in the model tool message and raw handler returns remain compatible.
- Recording migration/API tests prove existing rows read correctly and new rows preserve logical result, exact result text, and separate metadata.
- Memory presentation tests assert forbidden fields are absent for every memory kind.
- Binding tests prove every returned memory can be reconciled without exposing identity to the model.
- Recall tests prove due triggers and scoped context notes appear without an explicit search call and respect league/season/time scope.
- Stable-schema tests assert the same ordered tool definitions are sent before and after submission.
- Submission tests prove the article becomes immutable, the closeout procedure appears in the actual submission result, and the runner continues.
- Completion tests prove `complete_memory_review` cannot finish early, supports a no-op, and terminates after submission.
- Turn-budget tests prove closeout gets its bounded opportunity after a last-turn submission.
- Live/backtest tests prove closeout proposals use existing finalization and backtests do not mutate memory.
- Cutover tests prove removal of structured-brief fact buffering does not duplicate closeout writes.
- A sequential multi-week harness demonstrates at least one complete callback path: trigger saved during closeout, automatically recalled when due, used in an article, updated during closeout, and recalled later.
