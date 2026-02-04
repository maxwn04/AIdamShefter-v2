"""OpenAI Agents SDK tool definitions for the Sleeper data layer.

This module provides tool definitions compatible with the OpenAI Agents SDK.
Each tool maps to a method on SleeperLeagueData.

Usage with OpenAI Agents SDK:
    from agents import Agent
    from datalayer.tools import SLEEPER_TOOLS, create_tool_handlers

    data = SleeperLeagueData()
    data.load()

    agent = Agent(
        name="Fantasy Football Reporter",
        instructions="You are a fantasy football analyst...",
        tools=SLEEPER_TOOLS,
    )

    # In your tool handler:
    handlers = create_tool_handlers(data)
    result = handlers[tool_name](**arguments)
"""

from __future__ import annotations

from typing import Any, Callable

# Tool definitions in OpenAI function calling format
SLEEPER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_league_snapshot",
            "description": "Get a comprehensive snapshot of the league for a specific week. Returns standings, all matchup results, and transactions. Use this to get a high-level view of league state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "week": {
                        "type": "integer",
                        "description": "Week number (1-18). Omit for current week."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_week_games",
            "description": "Get all matchup games for a specific week with scores and winners. Returns a list of head-to-head matchups.",
            "parameters": {
                "type": "object",
                "properties": {
                    "week": {
                        "type": "integer",
                        "description": "Week number (1-18). Omit for current week."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_week_games_with_players",
            "description": "Get all matchup games for a specific week with full player-by-player breakdowns. Use this when you need to analyze individual player contributions to each game.",
            "parameters": {
                "type": "object",
                "properties": {
                    "week": {
                        "type": "integer",
                        "description": "Week number (1-18). Omit for current week."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_team_game",
            "description": "Get a specific team's game for a week. Returns the matchup with opponent, scores, and winner.",
            "parameters": {
                "type": "object",
                "properties": {
                    "roster_key": {
                        "type": "string",
                        "description": "Team identifier: team name (e.g., 'Schefter'), manager name, or roster_id as string."
                    },
                    "week": {
                        "type": "integer",
                        "description": "Week number (1-18). Omit for current week."
                    }
                },
                "required": ["roster_key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_team_game_with_players",
            "description": "Get a specific team's game for a week with full player-by-player breakdowns. Use this to analyze how each player contributed to the team's score.",
            "parameters": {
                "type": "object",
                "properties": {
                    "roster_key": {
                        "type": "string",
                        "description": "Team identifier: team name (e.g., 'Schefter'), manager name, or roster_id as string."
                    },
                    "week": {
                        "type": "integer",
                        "description": "Week number (1-18). Omit for current week."
                    }
                },
                "required": ["roster_key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_week_player_leaderboard",
            "description": "Get the top-scoring players for a specific week, ranked by fantasy points. Use this to identify standout performances and weekly MVPs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "week": {
                        "type": "integer",
                        "description": "Week number (1-18). Omit for current week."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum players to return. Default is 10."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_team_dossier",
            "description": "Get a comprehensive profile of a team including standings, record, streak, and last 5 games. Use this to understand a team's current situation and recent trajectory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "roster_key": {
                        "type": "string",
                        "description": "Team identifier: team name (e.g., 'Schefter'), manager name, or roster_id as string."
                    },
                    "week": {
                        "type": "integer",
                        "description": "Week number for standings. Omit for current week."
                    }
                },
                "required": ["roster_key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_team_schedule",
            "description": "Get the full season schedule for a team with game-by-game results. Shows all games with opponent, scores, results (W/L/T), and cumulative record after each week.",
            "parameters": {
                "type": "object",
                "properties": {
                    "roster_key": {
                        "type": "string",
                        "description": "Team identifier: team name (e.g., 'Schefter'), manager name, or roster_id as string."
                    }
                },
                "required": ["roster_key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_roster_current",
            "description": "Get a team's current roster composition. Returns all players organized by role (starter/bench) and position, plus draft picks owned.",
            "parameters": {
                "type": "object",
                "properties": {
                    "roster_key": {
                        "type": "string",
                        "description": "Team identifier: team name (e.g., 'Schefter'), manager name, or roster_id as string."
                    }
                },
                "required": ["roster_key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_roster_snapshot",
            "description": "Get a team's roster as it was during a specific week. Returns players with their points scored that week, organized by role and position. Use for historical lineup analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "roster_key": {
                        "type": "string",
                        "description": "Team identifier: team name (e.g., 'Schefter'), manager name, or roster_id as string."
                    },
                    "week": {
                        "type": "integer",
                        "description": "Week number (1-18) to query."
                    }
                },
                "required": ["roster_key", "week"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_transactions",
            "description": "Get all transactions (trades, waivers, free agent pickups) in a week range. Returns grouped transactions showing what each team sent and received.",
            "parameters": {
                "type": "object",
                "properties": {
                    "week_from": {
                        "type": "integer",
                        "description": "Starting week (inclusive)."
                    },
                    "week_to": {
                        "type": "integer",
                        "description": "Ending week (inclusive)."
                    }
                },
                "required": ["week_from", "week_to"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_team_transactions",
            "description": "Get a specific team's transactions in a week range. Returns trades, waivers, and FA pickups for that team only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "roster_key": {
                        "type": "string",
                        "description": "Team identifier: team name (e.g., 'Schefter'), manager name, or roster_id as string."
                    },
                    "week_from": {
                        "type": "integer",
                        "description": "Starting week (inclusive)."
                    },
                    "week_to": {
                        "type": "integer",
                        "description": "Ending week (inclusive)."
                    }
                },
                "required": ["roster_key", "week_from", "week_to"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_player_summary",
            "description": "Get basic metadata about an NFL player. Returns position, NFL team, status, and injury information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "player_key": {
                        "type": "string",
                        "description": "Player name (e.g., 'Patrick Mahomes') or player_id."
                    }
                },
                "required": ["player_key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_player_weekly_log",
            "description": "Get a player's full season fantasy performance log. Returns week-by-week points, role (starter/bench), and which fantasy team rostered them. Includes season totals and averages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "player_key": {
                        "type": "string",
                        "description": "Player name (e.g., 'Patrick Mahomes') or player_id."
                    }
                },
                "required": ["player_key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_player_weekly_log_range",
            "description": "Get a player's fantasy performance log for a specific week range. Use this to analyze performance over a subset of the season.",
            "parameters": {
                "type": "object",
                "properties": {
                    "player_key": {
                        "type": "string",
                        "description": "Player name (e.g., 'Patrick Mahomes') or player_id."
                    },
                    "week_from": {
                        "type": "integer",
                        "description": "Starting week (inclusive)."
                    },
                    "week_to": {
                        "type": "integer",
                        "description": "Ending week (inclusive)."
                    }
                },
                "required": ["player_key", "week_from", "week_to"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": "Execute a custom SELECT query for advanced analysis. Use this when the other tools don't provide the specific data you need. Only SELECT queries are allowed; write operations are blocked.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A SELECT SQL query. Available tables: leagues, season_context, team_profiles, rosters, roster_players, players, matchups, player_performances, games, standings, transactions, transaction_moves, draft_picks."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum rows to return. Default is 200."
                    }
                },
                "required": ["query"]
            }
        }
    },
]


def create_tool_handlers(data: "SleeperLeagueData") -> dict[str, Callable[..., Any]]:
    """Create a mapping of tool names to handler functions.

    Args:
        data: A loaded SleeperLeagueData instance.

    Returns:
        Dict mapping tool names to callable handlers.

    Example:
        data = SleeperLeagueData()
        data.load()
        handlers = create_tool_handlers(data)

        # When agent calls a tool:
        result = handlers["get_team_dossier"](roster_key="Schefter")
    """
    return {
        "get_league_snapshot": lambda week=None: data.get_league_snapshot(week),
        "get_week_games": lambda week=None: data.get_week_games(week),
        "get_week_games_with_players": lambda week=None: data.get_week_games_with_players(week),
        "get_team_game": lambda roster_key, week=None: data.get_team_game(roster_key, week),
        "get_team_game_with_players": lambda roster_key, week=None: data.get_team_game_with_players(roster_key, week),
        "get_week_player_leaderboard": lambda week=None, limit=10: data.get_week_player_leaderboard(week, limit),
        "get_team_dossier": lambda roster_key, week=None: data.get_team_dossier(roster_key, week),
        "get_team_schedule": lambda roster_key: data.get_team_schedule(roster_key),
        "get_roster_current": lambda roster_key: data.get_roster_current(roster_key),
        "get_roster_snapshot": lambda roster_key, week: data.get_roster_snapshot(roster_key, week),
        "get_transactions": lambda week_from, week_to: data.get_transactions(week_from, week_to),
        "get_team_transactions": lambda roster_key, week_from, week_to: data.get_team_transactions(roster_key, week_from, week_to),
        "get_player_summary": lambda player_key: data.get_player_summary(player_key),
        "get_player_weekly_log": lambda player_key: data.get_player_weekly_log(player_key),
        "get_player_weekly_log_range": lambda player_key, week_from, week_to: data.get_player_weekly_log_range(player_key, week_from, week_to),
        "run_sql": lambda query, limit=200: data.run_sql(query, limit=limit),
    }


# Type import for type hints only
if False:  # TYPE_CHECKING equivalent without import
    from datalayer.sleeper_data import SleeperLeagueData
