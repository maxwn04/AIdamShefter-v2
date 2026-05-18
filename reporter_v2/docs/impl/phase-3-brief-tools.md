# Phase 3: Brief Artifact Tools

**Goal:** Implement `save_fact`, `save_storyline`, `set_outline`, `set_style`,
`set_bias`, and `read_brief` as plain functions that operate on `ArtifactStore`
and log to `RunLog`.

**Files to create:**
- `reporter_v2/runner/tools/__init__.py`
- `reporter_v2/runner/tools/context.py`
- `reporter_v2/runner/tools/brief_tools.py`
- `reporter_v2/tests/test_brief_tools.py`

**Dependencies:** Phase 1 (schemas, state), Phase 2 (RunLog)

---

## Tool Function Signature Pattern

Every tool function follows the same pattern:
```python
def tool_name(ctx: ToolContext, *, **params) -> str:
```
Returns a JSON string (tool result content). The `ToolContext` provides access
to `artifacts`, `procedures`, `log`, and the current `turn`. The runner's
`ToolRegistry` (Phase 6) injects the context at dispatch time.

## `reporter_v2/runner/tools/context.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from reporter_v2.runner.state import ArtifactStore, ProcedureState
from reporter_v2.runner.run_log import RunLog

@dataclass
class ToolContext:
    artifacts: ArtifactStore
    procedures: ProcedureState
    log: RunLog
    turn: int = 0
```

## `reporter_v2/runner/tools/brief_tools.py`

```python
def save_fact(
    ctx: ToolContext, *,
    id: str, claim_text: str, data_refs: list[str],
    numbers: dict[str, Any] | None = None, category: str = "general",
) -> str:
    """Add a verified fact to the brief. Validates non-empty claim_text and data_refs."""
    # Validation: return error JSON if claim_text empty or data_refs empty
    # Upsert: if fact with same id exists, replace it
    # Bump revision
    # Log artifact_write
    # Return success JSON with fact id and brief revision

def save_storyline(
    ctx: ToolContext, *,
    id: str, headline: str, summary: str,
    supporting_fact_ids: list[str], priority: int = 2,
    tags: list[str] | None = None,
) -> str:
    """Add/update a storyline. Validates supporting_fact_ids reference existing facts."""
    # Validate all fact IDs exist in brief.facts
    # If invalid IDs, return error JSON listing which IDs are missing
    # Upsert storyline with revision_at_set = current revision (after bump)
    # Log artifact_write
    # Return success JSON

def set_outline(
    ctx: ToolContext, *,
    sections: list[dict[str, Any]],
) -> str:
    """Set the article outline. Bumps revision, records revision_at_set."""

def set_style(
    ctx: ToolContext, *,
    voice: str = "sports columnist", pacing: str = "moderate",
    humor_level: int = 1, formality: str = "casual",
) -> str:

def set_bias(
    ctx: ToolContext, *,
    favored_teams: list[str] | None = None,
    disfavored_teams: list[str] | None = None,
    intensity: int = 0, framing_rules: list[str] | None = None,
) -> str:

def read_brief(ctx: ToolContext) -> str:
    """Return the current brief as JSON, including staleness flags."""
    # Serialize brief to dict
    # Add staleness_info from brief.staleness_info()
    # Return as JSON string
```

## Tests

- `test_save_fact_valid` -- save a fact, verify it appears in brief, revision bumped
- `test_save_fact_empty_data_refs` -- verify error returned
- `test_save_fact_empty_claim` -- verify error returned
- `test_save_fact_upsert` -- save same id twice, verify replacement
- `test_save_storyline_valid` -- save with valid fact refs
- `test_save_storyline_invalid_fact_ids` -- verify error when referencing nonexistent facts
- `test_set_outline` -- set outline, verify revision_at_set
- `test_read_brief_staleness` -- set outline, add fact, read_brief, verify outline_stale flag
- `test_read_brief_no_staleness` -- set outline after all facts, verify no stale flag
