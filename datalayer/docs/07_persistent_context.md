# Persistent League Context

## Problem

The research agent has no memory between runs. Each invocation re-discovers storylines, team arcs, and league themes from scratch. This leads to repetitive research and misses multi-week narrative threads.

## Solution

A separate file-backed SQLite database (`context.db`) stores agent-generated context: storylines, team notes, and league-wide metadata. The existing fresh-load pattern for Sleeper API data is unchanged.

```
Sleeper API → [in-memory SQLite] → query tools (unchanged)
                                         ↕
                              [context.db] → context tools (new)
```

## Data Model

Three tables in `context.db`, scoped by `league_id` + `season`:

- **`storylines`** — Persistent narrative threads (e.g., "Team X's 5-game win streak"). Has lifecycle: `active` → `resolved` or `stale`. Priority 1-5.
- **`team_context`** — One row per team. Free-text narrative + outlook enum (`rebuilding`, `contending`, `middling`, `surging`, `fading`). Replaced each run.
- **`league_context`** — Key-value pairs for league-wide notes (season themes, trade deadline recaps, rivalry notes).
- **`context_meta`** — Schema versioning for auto-migration.

## Agent Flow

1. Agent calls `get_league_memory()` first — reads previous storylines, team context, league notes
2. Researches current week data using existing tools
3. Builds ReportBrief incorporating persistent context
4. Agent calls `save_storyline()`, `save_team_context()`, `save_league_note()` to update memory
5. Draft agent writes from brief (unchanged)

## Key Design Decisions

- **Separate DB file**: Context store uses its own SQLite connection, not the in-memory datalayer DB. This keeps the two systems decoupled.
- **DB location**: `.data/context.db` (project-local, gitignored). Single file supports multiple leagues via `league_id` scoping.
- **Stale detection**: Storylines not updated in N weeks (default 4) are auto-marked `stale` before research begins.
- **Roster resolution**: Context tools accept `roster_key` (team name, manager name, or roster_id) and resolve via the existing `resolve_roster_id()` function from the datalayer.
- **Week parameter**: All write operations take a `week` parameter for timestamping. This comes from `ReportConfig.time_range.week_end`.

## Files

- `datalayer/context_store.py` — `ContextStore` class with schema, migration, CRUD
- `datalayer/context_tools.py` — `CONTEXT_TOOLS` definitions + `create_context_tool_handlers()`
- `reporter/tools/registry.py` — `create_context_tools()` wraps handlers as Agents SDK tools
- `reporter/agent/reporter_agent.py` — `ResearchAgent` accepts optional `ContextStore`
- `reporter/app/runner.py` — Creates `ContextStore`, passes to `ReporterAgent`
