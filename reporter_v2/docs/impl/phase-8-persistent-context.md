# Phase 8: Persistent Context Tools

**Goal:** Implement tools that read/write persistent context (storylines, team
context, league notes) via `reporter_memory.ContextStore`.

**Files to create:**
- `reporter_v2/runner/tools/persistent_tools.py`
- `reporter_v2/tests/test_persistent_tools.py`

**Dependencies:** Phase 6 (ToolRegistry), `reporter_memory.ContextStore`

---

## Design

V2 adds **read tools** that v1 didn't have as explicit tools (v1 injected context
into the prompt). V2 makes them tool-callable so the model can load them on demand.

The backing store lives in `reporter_memory/` and uses schema `2.1`. Storyline
identity, storyline history, and persisted facts are scoped by
`(league_id, season, id)`. Legacy `.data/context.db` files are not migrated.

## `reporter_v2/runner/tools/persistent_tools.py`

```python
def register_persistent_tools(
    registry: ToolRegistry,
    context_store: ContextStore,
    week: int,
    resolve_roster_fn: Callable | None = None,
) -> None:
    """Register persistent context tools (save + load)."""

    def save_persistent_storyline(
        *, id: str, headline: str, summary: str, status: str,
        priority: int = 2, tags: list[str] | None = None,
        team_keys: list[str] | None = None,
    ) -> str:
        # Resolve team_keys to roster_ids
        # Call context_store.upsert_storyline(...)
        # Return JSON success

    def save_team_context(
        *, roster_key: str, narrative: str, outlook: str | None = None,
    ) -> str:
        # Call context_store.upsert_team_context(...)

    def save_league_note(*, key: str, value: str) -> str:
        # Call context_store.upsert_league_context(...)

    def load_persistent_storylines() -> str:
        # Return context_store.get_enriched_storylines(...) as JSON
        storylines = context_store.get_storylines()
        enriched = context_store.get_enriched_storylines(
            [s["id"] for s in storylines]
        )
        return json.dumps(enriched, default=str)

    def load_team_context() -> str:
        return json.dumps(context_store.get_all_team_context(), default=str)

    def load_league_notes() -> str:
        return json.dumps(context_store.get_league_context(), default=str)

    # Register all with specs ...
```

## Tests

- Use an in-memory SQLite `reporter_memory.ContextStore`
- `test_save_and_load_storyline` -- save, then load, verify round-trip
- `test_save_team_context` -- save and verify
- `test_load_empty_context` -- verify empty lists/dicts returned when nothing saved
