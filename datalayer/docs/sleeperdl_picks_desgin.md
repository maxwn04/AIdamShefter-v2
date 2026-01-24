Below is a self‑contained design doc tailored to your current codebase and conventions. It assumes **Ask mode** (no edits), so this is documentation only.

---

## Design Doc: Draft Picks as First‑Class Roster Assets

### Summary
Add a `draft_picks` table to represent **current pick ownership** per roster, seeded for the next 3 seasons and updated using Sleeper’s `traded_picks` endpoint. Picks remain **roster‑ID‑based** internally; `team_profiles` is used for end‑user names, matching existing patterns.

### Goals
- Represent **future draft picks** with season, round, original roster, and current roster.
- Seed **every roster** with picks for the next 3 seasons (e.g., 2026–2028 when league season is 2025).
- Apply `traded_picks` to update current ownership.
- Expose picks in roster outputs using **team names** only at query time.
- Keep data model consistent with `roster_id` as source of truth.

### Non‑Goals
- No pick valuation, expected order, or draft positions.
- No historical pick ownership timeline beyond transaction history (already modeled via `transaction_moves`).

---

## Current State (Relevant Code)
- `transaction_moves` already stores pick metadata for transaction history.  
  See `datalayer/sleeper_data/normalize/transactions.py`.
- There is **no current ownership state** for picks (no `draft_picks` table).
- Roster queries use `roster_id` internally and join `team_profiles` for display.  
  See `resolve_roster_id()` and `get_roster_current()` in `datalayer/sleeper_data/queries/defaults.py`.

---

## Proposed Schema

### New Table: `draft_picks`
**Purpose:** current pick ownership state.

**Columns**
- `season` TEXT NOT NULL
- `round` INTEGER NOT NULL
- `original_roster_id` INTEGER NOT NULL
- `current_roster_id` INTEGER NOT NULL
- `pick_id` TEXT NULL (if provided by Sleeper)
- `source` TEXT NULL (optional: “seed” or “traded”)

**Primary Key**
- If `pick_id` is stable: `(pick_id)`
- Else: `(league_id, season, round, original_roster_id)`

**Foreign Keys**
- `(league_id, original_roster_id)` → `rosters(league_id, roster_id)`
- `(league_id, current_roster_id)` → `rosters(league_id, roster_id)`

**Indexes**
- `idx_draft_picks_current` on `(league_id, current_roster_id)`
- `idx_draft_picks_original` on `(league_id, original_roster_id)`
- `idx_draft_picks_season_round` on `(league_id, season, round)`

---

## Data Flow

### 1) Seed Picks (Base State)
When loading a league:
- Determine base season `S` (usually `league.season`).
- For each roster in `rosters`, create picks for seasons `S+1`, `S+2`, `S+3`.
- For each season, create 1..`draft_rounds` picks:
  - `original_roster_id = roster_id`
  - `current_roster_id = roster_id`

**Notes**
- Need `draft_rounds`. If not already stored, extract from `raw_league["settings"]["draft_rounds"]` and persist (maybe `leagues` metadata JSON).
- This seeding occurs once per load.

### 2) Apply Traded Picks
- Fetch `GET /league/{league_id}/traded_picks`.
- For each traded pick row:
  - Identify the pick by `(season, round, roster_id)` or `draft_pick_id`.
  - Set `current_roster_id = owner_id`.
- Picks not present in traded list retain original ownership.

---

## API Integration

### New Sleeper API Endpoint
Add helper in `datalayer/sleeper_data/sleeper_api/endpoints.py`:
- `get_traded_picks(league_id) -> list[dict]`
  - uses `/league/{league_id}/traded_picks`

### Loader Changes (Conceptual)
In `SleeperLeagueData.load()`:
1. Load rosters, team profiles, etc. (existing).
2. Seed picks (new).
3. Fetch traded picks and update ownership (new).

---

## Query Surface

### Extend `get_roster_current`
Return picks alongside players:

**Proposed output structure**
```
{
  "team": ...,
  "players": [...],
  "picks": [
    {
      "season": "2026",
      "round": 1,
      "current_roster_id": 3,
      "original_roster_id": 7,
      "current_team_name": "The Sharks",
      "original_team_name": "Gridiron Kings"
    },
    ...
  ],
  "as_of_week": None,
  "found": True
}
```

**Implementation notes**
- Join `draft_picks` to `team_profiles` twice: once for `current_roster_id`, once for `original_roster_id`.
- Filter picks by `current_roster_id` matching requested roster.

### Optional: `get_team_dossier`
You can also add picks to `get_team_dossier` using the same join logic.

---

## Data Consistency & Identity

- **Internal source of truth:** `roster_id` for both `current` and `original`.
- **Display:** `team_profiles.team_name` (fallback to manager name) at query time.
- This matches how `resolve_roster_id()` and transactions are already modeled.

---

## Edge Cases / Risks
- If `draft_pick_id` is missing, composite key must be stable.
- `league.season` vs `state.league_season` in offseason: decide which defines “current.”  
  If you want next 3 seasons relative to the current league year, use `state.league_season`.
- Re‑loading data should be deterministic; if you want persistence, use upserts.

---

## Example SQL (Roster Picks)
```
SELECT
  dp.season,
  dp.round,
  dp.original_roster_id,
  dp.current_roster_id,
  tpo.team_name AS original_team_name,
  tpc.team_name AS current_team_name
FROM draft_picks dp
LEFT JOIN team_profiles tpo
  ON tpo.league_id = dp.league_id AND tpo.roster_id = dp.original_roster_id
LEFT JOIN team_profiles tpc
  ON tpc.league_id = dp.league_id AND tpc.roster_id = dp.current_roster_id
WHERE dp.league_id = :league_id
  AND dp.current_roster_id = :roster_id
ORDER BY dp.season ASC, dp.round ASC;
```

---

## Validation / Success Criteria
- Every roster has picks for the next 3 seasons in `draft_picks`.
- Traded picks update `current_roster_id` correctly.
- Roster query returns pick data with `season`, `round`, `current`, and `original` roster names.

---