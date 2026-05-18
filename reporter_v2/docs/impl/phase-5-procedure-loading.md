# Phase 5: Procedure Loading

**Goal:** Implement `load_procedure` with replacement semantics and procedure
file reading.

**Files to create:**
- `reporter_v2/runner/tools/procedure_tools.py`
- `reporter_v2/procedures/research.md` (placeholder)
- `reporter_v2/procedures/storyline.md` (placeholder)
- `reporter_v2/procedures/drafting.md` (placeholder)
- `reporter_v2/procedures/verification.md` (placeholder)
- `reporter_v2/tests/test_procedure_tools.py`

**Dependencies:** Phase 2 (RunLog), Phase 1 (state.ProcedureState)

---

## Key Design: Message Manipulation for Replacement Semantics

The `load_procedure` function does not directly manipulate messages. Instead, it:
1. Reads the procedure markdown file
2. Updates `ProcedureState.active`
3. Logs the switch to RunLog
4. Returns the procedure text as the tool result string

The **replacement semantics** (removing the previous procedure's tool result
message from the conversation) are handled in the **runner loop** (Phase 6).
The runner tracks which message index corresponds to the active procedure's
tool result and removes it before appending the new one.

## `reporter_v2/runner/tools/procedure_tools.py`

```python
PROCEDURE_DIR = Path(__file__).parent.parent.parent / "procedures"
VALID_PROCEDURES = {"research", "storyline", "drafting", "verification"}

def load_procedure(
    ctx: ToolContext, *, name: str,
) -> str:
    """Load a procedure by name. Returns the procedure text."""
    if name not in VALID_PROCEDURES:
        return json.dumps({
            "error": f"Unknown procedure: {name}. Valid: {sorted(VALID_PROCEDURES)}"
        })

    path = PROCEDURE_DIR / f"{name}.md"
    if not path.exists():
        return json.dumps({"error": f"Procedure file not found: {path}"})

    prev = ctx.procedures.active
    ctx.procedures.active = name
    ctx.log.add_procedure_switch(prev, name, turn=ctx.turn)

    return path.read_text()
```

## Tests

- `test_load_valid_procedure` -- load "research", verify text returned and state updated
- `test_load_invalid_procedure` -- load "bogus", verify error JSON
- `test_procedure_switch_logged` -- load two procedures, verify log entries
- `test_procedure_state_updated` -- verify `procedures.active` changes
- Uses `tmp_path` to create temporary procedure files for testing
