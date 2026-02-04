Comprehensive Datalayer Exploration Report

       1. Overall Structure and Organization

       The datalayer is organized as a Python-first, layered data pipeline that fetches Sleeper
       fantasy football league data, normalizes it, stores it in SQLite, and exposes a rich
       query interface:

       Sleeper API → Normalize → In-Memory SQLite → Query API → Reporter Agent / CLI

       Directory Structure (/Users/max/Projects/AIdamShefter-v2/datalayer/):
       - sleeper_api/ - HTTP client and endpoint wrappers
       - normalize/ - Raw JSON → canonical dataclass transformation
       - schema/ - Dataclass models and DDL generation
       - store/ - SQLite in-memory database operations
       - queries/ - Curated query helpers and SQL tools
       - sleeper_league_data.py - Main facade class
       - config.py - Configuration management
       - cli/ - Command-line interface
       - docs/ - Architecture and design documentation

       2. Data Sources and API Connections

       Sleeper API Endpoints (in
       /Users/max/Projects/AIdamShefter-v2/datalayer/sleeper_data/sleeper_api/endpoints.py):
       - get_league() - League metadata
       - get_league_users() - Player/manager information
       - get_league_rosters() - Team roster data
       - get_matchups() - Weekly matchup data
       - get_transactions() - Trade/waiver/FA pickup data
       - get_traded_picks() - Traded draft pick information
       - get_players() - NFL player database (sport-specific)
       - get_state() - Current league state (current week, season)

       HTTP Client Features (in sleeper_api/client.py):
       - Minimal GET-only wrapper around requests library
       - Local file-based caching with 1-day TTL (.cache/sleeper/)
       - Error handling with custom SleeperApiError exceptions
       - 10-second timeout defaults

       3. Key Classes, Models, and Schemas

       Canonical Dataclass Models (in schema/models.py):
       - League - League metadata (id, season, name, sport, playoff settings)
       - SeasonContext - Week context (computed week, override week, effective week, timestamp)
       - User - Manager/user info (user_id, display_name, avatar)
       - Roster - Team roster info (league_id, roster_id, owner_user_id)
       - RosterPlayer - Player roster assignments (league_id, roster_id, player_id, role)
       - TeamProfile - LLM-friendly team identity (team_name, manager_name, avatar_url)
       - DraftPick - Draft pick ownership tracking (original_roster_id, current_roster_id,
       round)
       - MatchupRow - Raw weekly matchup data (points by team per week)
       - PlayerPerformance - Individual player scoring (player_id, roster_id, week, points,
       role)
       - Game - Derived head-to-head matchup (matchup_id, team A/B rosters, scores, winner,
       is_playoffs)
       - Player - NFL player metadata (full_name, position, nfl_team, status, injury_status)
       - Transaction - Trade/waiver/FA transaction metadata
       - TransactionMove - Individual assets in transactions (player_id, direction, bid_amount,
       picks)
       - StandingsWeek - Weekly standings (wins, losses, ties, points_for/against, rank, streak)

       Schema DDL (in schema/ddl.py):
       - Registry of TableSpec definitions with columns, primary keys, foreign keys, and indexes
       - 14 tables with careful indexing for common queries
       - Foreign key constraints enforced

       4. Available Queries and Methods

       Core Facade Class - SleeperLeagueData (in sleeper_league_data.py):

       League-Wide Queries:
       - get_league_snapshot(week=None) - Standings, games, transactions for a week
       - get_week_games(week=None) - All matchups with scores and winners
       - get_week_games_with_players(week=None) - Matchups with player-by-player breakdown
       - get_week_player_leaderboard(week=None, limit=10) - Top scorers ranked by points

       Team Queries:
       - get_team_dossier(roster_key, week=None) - Profile, standings, recent games (accepts
       team name, manager name, or roster_id)
       - get_team_game(roster_key, week=None) - Specific team's matchup
       - get_team_game_with_players(roster_key, week=None) - Matchup with player breakdowns
       - get_team_schedule(roster_key) - Full season schedule with W/L/T records
       - get_roster_current(roster_key) - Current roster organized by role and position
       - get_roster_snapshot(roster_key, week) - Historical roster for a specific week
       - get_team_transactions(roster_key, week_from, week_to) - Team-specific transaction
       history

       Player Queries:
       - get_player_summary(player_key) - Basic metadata (position, nfl_team, status, injury) -
       accepts name or player_id
       - get_player_weekly_log(player_key) - Full season performance log with week-by-week
       points
       - get_player_weekly_log_range(player_key, week_from, week_to) - Performance for specific
       week range

       Transaction Queries:
       - get_transactions(week_from, week_to) - All trades, waivers, FA pickups in range
         - Returns grouped transactions with player/pick details and team involvement

       General Purpose:
       - run_sql(query, params=None, limit=200) - Guarded SQL execution for custom analysis
         - Prevents: INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, PRAGMA, ATTACH
         - Enforces limit clause
         - Returns: {columns, rows (list of tuples), row_count}

       Utility Methods:
       - load() - Fetch, normalize, and load all data into SQLite
       - save_to_file(output_path) - Export in-memory database to SQLite file
       - _get_effective_week(week=None) - Resolve effective week with override

       5. Tool Adapters and Agent-Facing Interfaces

       OpenAI Agents SDK Integration (in tools.py):

       SLEEPER_TOOLS - List of 16 tool definitions in OpenAI function-calling format:

       1. get_league_snapshot - League standings and games
       2. get_week_games - Matchup scores and winners
       3. get_week_games_with_players - Games with player details
       4. get_team_game - Specific team's matchup
       5. get_team_game_with_players - Team matchup with players
       6. get_week_player_leaderboard - Top scorers (customizable limit)
       7. get_team_dossier - Team profile, standings, recent games
       8. get_team_schedule - Full season schedule
       9. get_roster_current - Current team roster
       10. get_roster_snapshot - Historical roster view
       11. get_transactions - League-wide transactions
       12. get_team_transactions - Team-specific transactions
       13. get_player_summary - Player metadata
       14. get_player_weekly_log - Player season performance
       15. get_player_weekly_log_range - Player performance subset
       16. run_sql - Custom SQL queries

       Helper Function:
       - create_tool_handlers(data: SleeperLeagueData) - Returns dict mapping tool names to
       callable handlers

       All tools include:
       - Clear descriptions for agent context
       - Type-annotated parameters with descriptions
       - Flexible inputs (names, IDs, optional week specifications)
       - JSON-serializable outputs with "found" boolean and "as_of_week" context

       6. Additional Features

       Name Resolution System (in queries/_resolvers.py):
       - resolve_player_id(conn, player_key) - Accept player name or ID
       - resolve_roster_id(conn, league_id, roster_key) - Accept team name, manager name, or ID
       - Handles ambiguous matches and returns structured errors

       Normalization Pipeline (in normalize/):
       - 8 normalization modules handling: leagues, users, rosters, matchups, players,
       transactions, standings, draft picks
       - Derived entities: games (paired matchups), team profiles (LLM-friendly identities)
       - Transaction move parsing for complex multi-asset trades

       Configuration (in config.py):
       - SLEEPER_LEAGUE_ID - Required league identifier
       - SLEEPER_WEEK_OVERRIDE - Optional week override for testing/offseason

       CLI Interface (in cli/main.py):
       - load-export - Fetch and export to SQLite file
       - app - Interactive query interface with commands:
         - snapshot [week] - League snapshot
         - games [week] - Weekly games
         - team <roster_id> [week] - Team dossier
         - roster <roster_id> [week] - Roster view
         - transactions <week_from> <week_to> - Transactions
         - player <player_id> [week_to] - Player log
         - sql <select_query> - Custom SQL
         - help, exit, quit

       7. Design Principles

       1. In-memory SQLite - Fast loads, rich joins, no persistence complexity
       2. Dataclasses as schema - Single source of truth for normalized data shape
       3. Query-time joins - Names kept current via joins, not denormalization
       4. Name resolution - Accept inputs by name/ID, return readable outputs
       5. Guarded SQL - Safe exploration without write operations
       6. Week override - Environment variable for offseason and testing
       7. Reporter-friendly outputs - Stable JSON contracts with human-readable names and
       "as_of_week" context

       8. What's Available for Reporter Agent Tools

       The datalayer is production-ready for exposing as tools to an AI reporter agent:

       - 16 curated query methods covering league, team, player, and transaction analysis
       - Flexible name-based inputs (team name, manager name, player name, or IDs)
       - Consistent output contracts with "found" boolean and "as_of_week" context
       - OpenAI Agents SDK integration already defined in tools.py
       - Safe custom SQL for agent exploration
       - Rich temporal context (week-by-week snapshots, historical rosters, performance logs)
       - Complete transaction tracking including draft picks and complex multi-asset trades

       All tools return JSON-serializable dictionaries suitable for LLM analysis without
       requiring additional formatting or translation layers.
