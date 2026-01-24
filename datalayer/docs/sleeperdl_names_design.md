---

# Design Doc: Name-Enriched Outputs + Name-Based Query Inputs

## Goal
Make the data layer reporter‑friendly by:
1) **Returning human‑readable names alongside IDs** in any query that surfaces players or rosters.  
2) **Allowing queries to accept names** (player or team) in addition to IDs, while **keeping IDs as the canonical foreign keys**.

This makes it easier for the AI reporter to attribute events to people/teams without additional lookups, while preserving relational integrity.

## Current State (Relevant Files)
- `datalayer/sleeper_data/schema/ddl.py` defines normalized tables and FKs.
- `datalayer/sleeper_data/queries/defaults.py` already enriches some outputs (e.g., games & standings) with team names but not consistently across all queries.

## Queries That Benefit Most
**Highest value (current returns are ID‑only):**
- `get_transactions` (adds player and team names for moves)
- `get_team_dossier` (should accept team name as input)
- `get_player_summary` (should accept player name as input)

**Already partially enriched (but can be standardized):**
- `get_week_games` (already returns team/manager names)
- `get_league_snapshot` (already returns team/manager names in standings)

## Proposed Approach

### 1) Keep IDs as source of truth (no denormalization)
- **Do not store duplicate names in transaction rows or matchup rows.**
- Use joins in query helpers to include `player_name` and `team_name`.

### 2) Add name resolution helpers
Create resolver functions so all queries can accept either ID or name:

- `resolve_player_id(conn, player_key)`
  - If `player_key` looks like an ID, return it
  - Else query `players` by `full_name`
  - If ambiguous (multiple matches), return “multiple matches” or require disambiguation

- `resolve_roster_id(conn, league_id, roster_key)`
  - If `roster_key` is numeric, treat as roster_id
  - Else query `team_profiles` by `team_name` (and/or `manager_name`)
  - Handle ambiguity explicitly

### 3) Enrich outputs with names (consistent contract)
Any query output that includes:
- `player_id` → also include `player_name`
- `roster_id` → also include `team_name` (and optionally `manager_name`)

### 4) Add lookup indexes for name-based queries
Add indices for faster resolution:
- `players.full_name`
- `team_profiles.team_name`
- `team_profiles.manager_name`

### 5) Define ambiguity & null handling
- If name lookup returns multiple rows, return a structured “multiple matches” response.
- If no match, return `{found: False}` with the provided key.

## Design Choices & Rationale

**Choice: query‑time joins vs. denormalizing names into fact tables**  
- Joins keep names current if a team is renamed or a player’s name updates.
- Denormalization adds write complexity and data drift risk.

**Choice: resolver helpers vs. SQL OR filters**  
- Resolver functions centralize behavior and avoid ambiguous SQL predicates.
- Easier to improve over time (e.g., fuzzy matching, nickname mapping).

**Choice: explicit ambiguity handling**  
- Names are not unique.
- Returning “multiple matches” is safer for the AI reporter than guessing.

**Choice: output contract standardization**  
- Stable fields reduce downstream parsing complexity.
- Ensures consistent UX for the AI reporter across queries.

## Suggested Implementation Plan (High Level)

1) **Add resolver helpers** in `datalayer/sleeper_data/queries/`  
2) **Update query helpers** to:
   - Accept `name_or_id` params
   - Resolve to IDs
   - Join names in outputs  
3) **Add indices** in `DDL_REGISTRY`  
4) **Update docs / README** to describe new parameters and return shapes  

## Implementation Notes (Defaults Queries)
- `get_player_summary(conn, player_key, week_to=None)` accepts player ID or `full_name`
  - Returns `{found: False, player_key: ..., matches: [...]}` for ambiguity
- `get_team_dossier(conn, league_id, roster_key, week=None)` accepts roster ID or team/manager name
  - Returns `{found: False, roster_key: ..., matches: [...]}` for ambiguity
- `get_transactions(conn, week_from, week_to)` now includes `player_name`, `team_name`, `manager_name`

## Example Output Contract (Transactions)
```json
{
  "transaction_id": "123",
  "type": "add",
  "player_id": "9876",
  "player_name": "CeeDee Lamb",
  "roster_id": 4,
  "team_name": "Dallas Dynasty",
  "manager_name": "Alex"
}
```

---

If you want, I can also provide a **specific outline of code changes** for `defaults.py` (resolver functions + SQL updates) and for the `DDL_REGISTRY` indexes.