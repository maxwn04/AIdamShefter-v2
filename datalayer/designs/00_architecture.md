 # Datalayer Architecture
 
 ## Purpose
 
 This datalayer provides a clean, queryable view of a Sleeper fantasy football league.
 It is built to serve downstream consumers such as an AI fantasy football reporter, while
 remaining a developer-friendly system for extension and analysis.
 
 ## High-Level Architecture
 
 The system follows a layered pipeline that converts raw API responses into a stable,
 relational model and exposes curated query methods.
 
 1. Fetch raw JSON from the Sleeper API.
 2. Normalize raw data into canonical dataclasses.
 3. Load normalized rows into an in-memory SQLite schema.
 4. Expose queries that return enriched, reporter-ready data shapes.
 
 ```mermaid
 flowchart LR
   SleeperAPI[ SleeperAPI ] --> Normalize[ Normalize ]
   Normalize --> SQLiteStore[ SQLiteStore ]
   SQLiteStore --> QueryAPI[ QueryAPI ]
   QueryAPI --> ReporterConsumers[ ReporterConsumers ]
 ```
 
 ## Core Entry Point
 
 `SleeperLeagueData` is the facade that orchestrates loading and querying. It:
 - Resolves the effective week (computed or override).
 - Orchestrates fetch → normalize → store.
 - Exposes high-level query methods and guarded SQL access.
 
 ## Design Rationale
 
 - **In-memory SQLite** keeps loads fast and enables rich joins without persistence
   complexity during early iteration.
 - **Dataclasses-as-schema** provide a single source of truth for data shape and
   simplify table generation and bulk inserts.
 - **Query-time joins** avoid denormalized name fields and keep identities current
   without write-time maintenance.
 - **Name resolution** allows inputs by name or ID, producing human-readable outputs
   that are suitable for narrative generation.
 - **Guarded SQL access** supports exploration while preventing writes and unbounded
   queries in agent workflows.
 - **Unified transaction assets + draft pick ownership** provide a coherent view of
   roster movement and pick state.
 
 ## AI Reporter Context (Developer-Facing)
 
 The datalayer emphasizes stable, enriched outputs that downstream narrative systems
 can depend on. Queries return readable names (manager, team, player) and include temporal
 context such as `as_of_week`, enabling consistent, explainable story generation without
 embedding reporter logic in this layer.
 
 ## Key Modules
 
 - Facade and orchestration: [c:\Users\maxwn\AIdamShefter-v2\datalayer\sleeper_data\sleeper_league_data.py](c:\Users\maxwn\AIdamShefter-v2\datalayer\sleeper_data\sleeper_league_data.py)
 - API client and endpoints: [c:\Users\maxwn\AIdamShefter-v2\datalayer\sleeper_data\sleeper_api](c:\Users\maxwn\AIdamShefter-v2\datalayer\sleeper_data\sleeper_api)
 - Normalization pipeline: [c:\Users\maxwn\AIdamShefter-v2\datalayer\sleeper_data\normalize](c:\Users\maxwn\AIdamShefter-v2\datalayer\sleeper_data\normalize)
 - Canonical schema models: [c:\Users\maxwn\AIdamShefter-v2\datalayer\sleeper_data\schema\models.py](c:\Users\maxwn\AIdamShefter-v2\datalayer\sleeper_data\schema\models.py)
 - DDL generation: [c:\Users\maxwn\AIdamShefter-v2\datalayer\sleeper_data\schema\ddl.py](c:\Users\maxwn\AIdamShefter-v2\datalayer\sleeper_data\schema\ddl.py)
 - SQLite store: [c:\Users\maxwn\AIdamShefter-v2\datalayer\sleeper_data\store\sqlite_store.py](c:\Users\maxwn\AIdamShefter-v2\datalayer\sleeper_data\store\sqlite_store.py)
 - Default queries: [c:\Users\maxwn\AIdamShefter-v2\datalayer\sleeper_data\queries\defaults.py](c:\Users\maxwn\AIdamShefter-v2\datalayer\sleeper_data\queries\defaults.py)
 - Guarded SQL tool: [c:\Users\maxwn\AIdamShefter-v2\datalayer\sleeper_data\queries\sql_tool.py](c:\Users\maxwn\AIdamShefter-v2\datalayer\sleeper_data\queries\sql_tool.py)
 - Configuration: [c:\Users\maxwn\AIdamShefter-v2\datalayer\sleeper_data\config.py](c:\Users\maxwn\AIdamShefter-v2\datalayer\sleeper_data\config.py)
 - CLI entrypoint: [c:\Users\maxwn\AIdamShefter-v2\datalayer\cli\main.py](c:\Users\maxwn\AIdamShefter-v2\datalayer\cli\main.py)
 
 ## Related Design Docs
 
 - [c:\Users\maxwn\AIdamShefter-v2\datalayer\designs\01_datalayer.md](c:\Users\maxwn\AIdamShefter-v2\datalayer\designs\01_datalayer.md)
 - [c:\Users\maxwn\AIdamShefter-v2\datalayer\designs\02_surfacing_names.md](c:\Users\maxwn\AIdamShefter-v2\datalayer\designs\02_surfacing_names.md)
 - [c:\Users\maxwn\AIdamShefter-v2\datalayer\designs\03_picks.md](c:\Users\maxwn\AIdamShefter-v2\datalayer\designs\03_picks.md)
 - [c:\Users\maxwn\AIdamShefter-v2\datalayer\designs\04_transactions.md](c:\Users\maxwn\AIdamShefter-v2\datalayer\designs\04_transactions.md)
