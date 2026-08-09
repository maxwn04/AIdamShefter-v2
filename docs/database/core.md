# Core Namespace Schema

**Status:** Simplified hardened design  
**PostgreSQL namespace:** `core`  
**Compatibility:** Clean replacement

## Validation Ownership

DB-028 governs implementation. PostgreSQL enforces identity, nullability,
natural uniqueness, same-competition foreign keys, and restrictive deletion.
Pydantic resource objects validate display-name/identifier text, season-year
ranges, and positive sequence numbers.

## Purpose

`core` owns only the product identities required to connect a dynasty league
across Sleeper seasons:

- a competition representing the league over its lifetime;
- an ordered competition season mapped to one Sleeper league ID;
- a franchise representing one durable team identity;
- a season roster connecting that franchise to one season's Sleeper roster ID.

It does not model managers, provider registries, identity candidates, aliases,
name history, franchise mergers, or provider migration. Those are legitimate
future features, but none is needed to preserve the current agent behavior or
build the first platform UI.

## Tool-Facing Identity

The reporter tools need a small stable vocabulary:

| Identity | Meaning shown to tools |
| --- | --- |
| `competition_id` | The dynasty/league across all seasons |
| `competition_season_id` | One season of that competition |
| `season_year` | Human-readable football season |
| `sequence_number` | Explicit ordering within the dynasty |
| `franchise_id` | The durable team across seasons |
| `season_roster_id` | That franchise's roster in one season |

Tools should normally render names and season labels, while returning these IDs
where follow-up calls need unambiguous references. Sleeper user IDs and manager
display names are observed data in `sleeper`; they are not separate core people.

## Tables

### `core.competitions`

One durable league identity:

- `id uuid` primary key;
- `display_name text`;
- `created_at timestamptz`;
- `updated_at timestamptz`;
- nullable `archived_at timestamptz`.

Names are not unique. `archived_at` is the only lifecycle field. There is no
status matrix or name-history table in the baseline. `display_name` is mutable
UI metadata; `updated_at` records that mutation without pretending to preserve
a complete name history.

### `core.competition_seasons`

One ordered season:

- `id uuid` primary key;
- `competition_id` foreign key;
- `season_year smallint`;
- positive `sequence_number smallint`;
- `sleeper_league_id text`;
- `created_at timestamptz`.

Constraints:

- unique `(competition_id, season_year)`;
- unique `(competition_id, sequence_number)`;
- unique `(id, competition_id)` to support same-competition composite foreign
  keys;
- unique `sleeper_league_id`;
- a practical season-year range validated by the application;
- `ON DELETE RESTRICT` from the competition.

`starts_on` and `ends_on` are intentionally absent. Fetch behavior comes from
the requested season, Sleeper league status/state, and explicit refresh inputs;
calendar guesses should not decide whether ingestion runs. Sleeper's
`previous_league_id` is useful setup evidence but not a core invariant.

`sequence_number` is the authoritative dynasty order. It normally follows
`season_year`, but it may intentionally differ when imported history skips a
season or the product later supports a non-calendar competition. Code must not
silently recalculate it from the year.

### `core.franchises`

One durable team identity inside a competition:

- `id uuid` primary key;
- `competition_id` foreign key;
- `display_name text`;
- `created_at timestamptz`;
- `updated_at timestamptz`;
- nullable `archived_at timestamptz`.

Duplicate names are valid. The baseline assumes franchises remain consistent.
There is no merged status, manager membership, alias table, or name history.
Those can be introduced additively if real usage demonstrates the need.
The display name is current mutable UI metadata and updates `updated_at`.
Unique `(id, competition_id)` supports same-competition composite foreign keys.

### `core.season_rosters`

The intentional seam between annual Sleeper rosters and durable franchises:

- `id uuid` primary key;
- `competition_id` foreign key;
- `competition_season_id` foreign key;
- `franchise_id` foreign key;
- `sleeper_roster_id text`;
- `created_at timestamptz`.

Constraints:

- unique `(competition_season_id, sleeper_roster_id)`;
- unique `(competition_season_id, franchise_id)`;
- unique `(id, competition_season_id)` and unique `(id, competition_id)` where
  downstream composite scope checks need them;
- composite foreign keys ensure the season and franchise belong to the same
  competition;
- all durable references use `ON DELETE RESTRICT`.

This table is deliberately simpler than a roster-slot reconciliation system.
On the first season, setup creates one franchise for each roster. A later season
maps each roster to an existing franchise or creates a new franchise. Ambiguous
mapping is resolved during setup rather than persisted as candidate/status
workflow tables. Raw Sleeper requests remain available if setup must be retried.

## What “Manager” Means for Now

The product uses franchise identity as the durable team concept. Sleeper user
profiles and the owner/co-owner IDs returned with a roster provide the displayed
manager information for that season.

This intentionally does not attempt to answer whether two Sleeper accounts are
the same person, the precise date ownership changed, or whether a franchise
changed hands. If those become product requirements, add a manager identity and
temporal franchise-membership tables without changing existing franchise or
season-roster IDs.

## Sleeper-Specific Baseline

Sleeper is the only provider. The schema uses explicit fields such as
`sleeper_league_id`, `sleeper_roster_id`, and `sleeper_user_id`; there is no
provider or provider-namespace table.

Fetching still uses a code-level interface so another provider can implement
the same service contract later. A future provider migration would add source
mapping tables and backfill every existing row as Sleeper. Building those joins
and reconciliation states now would not improve the current product.

## Tool and Snapshot Behavior

Frozen reporter snapshots resolve provider rows to core IDs and expose:

- dynasty and season identity;
- season ordering;
- the season roster and durable franchise together;
- the display names actually selected for that run;
- Sleeper owner names as observed data rather than durable person identity.

The agent does not receive mapping candidates, churn history, aliases, or
provider abstractions. This keeps its current mental model intact while allowing
cross-season queries and storylines.

## Indexing and Deletion

Baseline indexes cover:

- competition seasons by competition and sequence;
- franchises by competition and archive state;
- season rosters by season, franchise, and Sleeper roster ID;
- the unique Sleeper league ID lookup used by refresh entry points.

Normal product behavior archives competitions or franchises. Hard deletion is
limited to disposable development/test environments; facts, memory, and
generations restrict deletion of referenced core rows.

## Deferred Seams

Explicitly deferred:

- manager/person identity and ownership history;
- franchise merges and splits;
- team/manager name history;
- provider registries and cross-provider migrations;
- mapping-candidate and reconciliation audit workflows;
- season start/end dates and lifecycle state;
- generalized sports support.

The stable competition, competition-season, franchise, and season-roster UUIDs
are the seam that makes those additions possible later. No additional baseline
identity machinery is required.
