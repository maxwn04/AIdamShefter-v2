Below is a full, self‑contained design doc for **Option A** (single `transaction_moves` table with explicit pick metadata).

---

## Design Doc: Option A — Unified Transaction Assets with Pick Metadata

### Summary
Store **all transaction assets** (players + picks) in `transaction_moves` and extend it with pick‑specific fields. Keep `transactions` as the parent record. This enables SQL aggregation of the entire trade without additional relations, while retaining enough detail to describe draft picks accurately.

### Goals
- Represent **players and draft picks in one table**.
- Make `roster_id` consistently represent the roster involved (sender/receiver).
- Include draft pick detail (season, round, original roster).
- Support **single‑row aggregated output** per transaction in SQL.
- Keep schema changes minimal and query‑friendly.

### Non‑Goals
- No derived analytics or valuations.
- No materialized aggregates.
- No additional transaction grouping table.

---

## Current Model (as‑is)
Tables:
- `transactions` (parent)
- `transaction_moves` (child; one row per move)
- `players`, `team_profiles` for lookups

Current `transaction_moves` fields:
- `transaction_id`, `roster_id`, `player_id`, `direction`, `bid_amount`, `from_roster_id`, `to_roster_id`

Problem:
- Draft picks are stored as `direction="pick"` but **no pick metadata** (round/season/original owner).
- `roster_id` is set to pick owner only; sender is `from_roster_id`, which is not included in roster‑filtered queries.

---

## Proposed Schema Changes (Option A)

### 1) Extend `transaction_moves`
Add explicit fields for pick metadata **and** asset type:

**New columns**
- `asset_type` TEXT NOT NULL  
  - values: `"player"`, `"pick"`
- `pick_season` TEXT NULL  
- `pick_round` INTEGER NULL  
- `pick_original_roster_id` INTEGER NULL  
- `pick_id` TEXT NULL (optional if Sleeper supplies)

**Existing columns continue**
- `player_id` remains nullable; only set for player assets
- `from_roster_id` / `to_roster_id` continue to represent the movement direction

**Why explicit columns instead of JSON?**
- SQL aggregation becomes simpler and faster.
- Indexing/filtering is easier (e.g., “all 2026 1st round picks”).

If you prefer JSON for flexibility, use `pick_metadata_json` instead of explicit columns, but the design below assumes explicit columns.

---

## Normalization Changes

### Player Moves
Unchanged logic:
- `asset_type="player"`
- `player_id` populated
- `direction`: `add` / `drop`
- `roster_id`: roster involved

### Draft Pick Moves
When normalizing `raw_tx["draft_picks"]`:

**Create two rows per pick**
1) **Pick sent**  
   - `asset_type="pick"`
   - `direction="pick_out"`
   - `roster_id = previous_owner_id`
   - `from_roster_id = previous_owner_id`
   - `to_roster_id = owner_id`

2) **Pick received**  
   - `asset_type="pick"`
   - `direction="pick_in"`
   - `roster_id = owner_id`
   - `from_roster_id = previous_owner_id`
   - `to_roster_id = owner_id`

**Pick metadata fields**
- `pick_season = pick["season"]`
- `pick_round = pick["round"]`
- `pick_original_roster_id = pick["roster_id"]`
- `pick_id = pick.get("draft_pick_id")` (if available)

This guarantees `roster_id` always maps to “the roster whose view this move belongs to.”

---

## SQL Aggregation (One Row Per Transaction)

### Output Shape (example)
```
{
  transaction_id,
  week,
  type,
  status,
  created_ts,
  assets: [
    {
      asset_type,
      direction,
      roster_id,
      player_id,
      player_name,
      pick_season,
      pick_round,
      pick_original_roster_id,
      from_roster_id,
      to_roster_id
    }, ...
  ]
}
```

### Query (conceptual)
```
SELECT
  t.transaction_id,
  t.week,
  t.type,
  t.status,
  t.created_ts,
  json_group_array(
    json_object(
      'asset_type', tm.asset_type,
      'direction', tm.direction,
      'roster_id', tm.roster_id,
      'player_id', tm.player_id,
      'player_name', p.full_name,
      'pick_season', tm.pick_season,
      'pick_round', tm.pick_round,
      'pick_original_roster_id', tm.pick_original_roster_id,
      'from_roster_id', tm.from_roster_id,
      'to_roster_id', tm.to_roster_id
    )
  ) AS assets_json
FROM transactions t
LEFT JOIN transaction_moves tm
  ON tm.transaction_id = t.transaction_id
LEFT JOIN players p
  ON p.player_id = tm.player_id
WHERE t.week BETWEEN :week_from AND :week_to
GROUP BY t.transaction_id
ORDER BY t.week DESC, t.created_ts DESC;
```

### Roster Filtering
To return transactions **relevant to a roster**, filter on:
- `tm.roster_id = :roster_id`  
This works now because each roster has its own “in/out” pick rows.

---

## Indexing
Add or update index:
- `idx_transaction_moves_tx` already exists on `transaction_id`
- Recommended: `idx_transaction_moves_roster` on `roster_id` for roster‑filtered queries

---

## Backward Compatibility
- Backward Compatibility is not needed
- Replace old get_transactions with new function

---

## Migration Notes
If you already have stored transaction moves:
- Re‑ingest historical transactions to populate pick metadata.
- Or leave historic rows and accept that old picks won’t have full detail.

---

## Validation / Success Criteria
- For any trade with picks, aggregated transaction includes:
  - season + round
  - original roster id
  - both sides reflected by `pick_in` and `pick_out`
- Filtering by roster includes picks sent away.
- Aggregated output has full asset list per transaction.

