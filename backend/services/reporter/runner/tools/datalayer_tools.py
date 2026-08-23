"""Reporter-owned tools over one frozen league-data snapshot."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from backend.services.reporter.runner.models import ToolDef
from backend.services.reporter.runner.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from backend.services.datalayer import FrozenLeagueData


DATALAYER_TOOL_IMPLEMENTATION_VERSION = "1"


def _week_property(description: str = "Week number (1-18).") -> dict[str, str]:
    return {"type": "integer", "description": description}


def _roster_property() -> dict[str, str]:
    return {
        "type": "string",
        "description": "Team name, manager name, or roster_id as a string.",
    }


def _tool(
    name: str,
    description: str,
    properties: dict[str, dict[str, Any]],
    required: tuple[str, ...] = (),
) -> ToolDef:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(required),
            },
        },
    }


DATALAYER_TOOL_SPECS: list[ToolDef] = [
    _tool(
        "league_snapshot",
        "Get a comprehensive league snapshot for a week, including standings, "
        "matchup results, and transactions.",
        {"week": _week_property("Week number. Omit for snapshot cutoff.")},
    ),
    _tool(
        "week_games",
        "Get every matchup for a week with full player-by-player breakdowns.",
        {"week": _week_property("Week number. Omit for snapshot cutoff.")},
    ),
    _tool(
        "team_game",
        "Get one team's game for a week with full player-by-player breakdowns.",
        {
            "roster_key": _roster_property(),
            "week": _week_property("Week number. Omit for snapshot cutoff."),
        },
        ("roster_key",),
    ),
    _tool(
        "week_player_leaderboard",
        "Get the top-scoring players for a week, ranked by fantasy points.",
        {
            "week": _week_property("Week number. Omit for snapshot cutoff."),
            "limit": {
                "type": "integer",
                "description": "Maximum players to return. Default is 10.",
            },
        },
    ),
    _tool(
        "team_dossier",
        "Get a team profile with standings, record, streak, and recent games.",
        {
            "roster_key": _roster_property(),
            "week": _week_property(
                "Week number for standings. Omit for snapshot cutoff."
            ),
        },
        ("roster_key",),
    ),
    _tool(
        "team_schedule",
        "Get a team's snapshot-bounded schedule with opponents, scores, results, "
        "and cumulative record.",
        {"roster_key": _roster_property()},
        ("roster_key",),
    ),
    _tool(
        "roster_at_cutoff",
        "Get a team's roster composition at the selected snapshot cutoff, organized "
        "by role and position, plus draft picks owned.",
        {"roster_key": _roster_property()},
        ("roster_key",),
    ),
    _tool(
        "roster_snapshot",
        "Get a team's roster and player scores during a specific week.",
        {
            "roster_key": _roster_property(),
            "week": _week_property("Week number to query."),
        },
        ("roster_key", "week"),
    ),
    _tool(
        "transactions",
        "Get all grouped trades, waivers, and free-agent pickups in a week range.",
        {
            "week_from": _week_property("Starting week (inclusive)."),
            "week_to": _week_property("Ending week (inclusive)."),
        },
        ("week_from", "week_to"),
    ),
    _tool(
        "team_transactions",
        "Get one team's trades, waivers, and free-agent pickups in a week range.",
        {
            "roster_key": _roster_property(),
            "week_from": _week_property("Starting week (inclusive)."),
            "week_to": _week_property("Ending week (inclusive)."),
        },
        ("roster_key", "week_from", "week_to"),
    ),
    _tool(
        "bench_analysis",
        "Get starter-versus-bench scoring for a week, league-wide or for one team.",
        {
            "roster_key": {
                "type": "string",
                "description": "Optional team identifier. Omit for league-wide mode.",
            },
            "week": _week_property("Week number. Omit for snapshot cutoff."),
        },
    ),
    _tool(
        "standings",
        "Get league standings, records, points, rank, and streaks for a week.",
        {"week": _week_property("Week number. Omit for snapshot cutoff.")},
    ),
    _tool(
        "player_summary",
        "Get an NFL player's snapshot metadata, including position, team, status, "
        "and injury information.",
        {
            "player_key": {
                "type": "string",
                "description": "Player name or player_id.",
            }
        },
        ("player_key",),
    ),
    _tool(
        "player_weekly_log",
        "Get a player's weekly fantasy points, lineup role, fantasy team, totals, "
        "and averages.",
        {
            "player_key": {
                "type": "string",
                "description": "Player name or player_id.",
            },
            "week_from": _week_property(
                "Starting week (inclusive). Omit for full snapshot."
            ),
            "week_to": _week_property(
                "Ending week (inclusive). Omit for full snapshot."
            ),
        },
        ("player_key",),
    ),
    _tool(
        "season_leaders",
        "Get top players across the snapshot by total or average fantasy points, with "
        "optional week, position, team, and role filters.",
        {
            "week_from": _week_property(
                "Starting week (inclusive). Omit for full snapshot."
            ),
            "week_to": _week_property(
                "Ending week (inclusive). Omit for full snapshot."
            ),
            "position": {
                "type": "string",
                "description": "Filter to a single position.",
            },
            "roster_key": {
                "type": "string",
                "description": "Filter to one team's players.",
            },
            "role": {
                "type": "string",
                "description": "Filter by lineup role.",
                "enum": ["starter", "bench"],
            },
            "sort_by": {
                "type": "string",
                "description": "Rank by total or average points.",
                "enum": ["total", "avg"],
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results. Default 10, maximum 30.",
            },
        },
    ),
    _tool(
        "playoff_bracket",
        "Get playoff bracket structure, results, progression, and placements from the "
        "selected snapshot.",
        {
            "bracket_type": {
                "type": "string",
                "description": "Filter to winners or losers. Omit for both.",
                "enum": ["winners", "losers"],
            }
        },
    ),
    _tool(
        "team_playoff_path",
        "Get one team's playoff opponents, results, placement, and elimination or "
        "championship status.",
        {"roster_key": _roster_property()},
        ("roster_key",),
    ),
    _tool(
        "run_sql",
        "Execute one guarded read-only query against the selected frozen SQLite "
        "snapshot for advanced analysis.",
        {
            "query": {
                "type": "string",
                "description": (
                    "A single SELECT query. Available tables: leagues, "
                    "season_context, users, rosters, team_profiles, draft_picks, "
                    "players, matchups, player_performances, games, roster_players, "
                    "transactions, transaction_moves, playoff_matchups, standings, "
                    "and snapshot_metadata."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Maximum rows to return. Default is 200.",
            },
        },
        ("query",),
    ),
]


def register_datalayer_tools(
    registry: ToolRegistry,
    data: FrozenLeagueData,
) -> None:
    """Register reporter data tools over an already-open frozen snapshot."""
    handlers = _create_tool_handlers(data)
    for spec in DATALAYER_TOOL_SPECS:
        name = spec["function"]["name"]
        registry.register(
            name,
            _json_handler(handlers[name]),
            spec,
            DATALAYER_TOOL_IMPLEMENTATION_VERSION,
        )


def _create_tool_handlers(
    data: FrozenLeagueData,
) -> dict[str, Callable[..., Any]]:
    return {
        "league_snapshot": lambda week=None: data.get_league_snapshot(week),
        "week_games": lambda week=None: data.get_week_games_with_players(week),
        "team_game": lambda roster_key, week=None: (
            data.get_team_game_with_players(roster_key, week)
        ),
        "week_player_leaderboard": lambda week=None, limit=10: (
            data.get_week_player_leaderboard(week, limit)
        ),
        "team_dossier": lambda roster_key, week=None: (
            data.get_team_dossier(roster_key, week)
        ),
        "team_schedule": lambda roster_key: data.get_team_schedule(roster_key),
        "roster_at_cutoff": lambda roster_key: data.get_roster_at_cutoff(roster_key),
        "roster_snapshot": lambda roster_key, week: (
            data.get_roster_snapshot(roster_key, week)
        ),
        "transactions": lambda week_from, week_to: (
            data.get_transactions(week_from, week_to)
        ),
        "team_transactions": lambda roster_key, week_from, week_to: (
            data.get_team_transactions(roster_key, week_from, week_to)
        ),
        "bench_analysis": lambda roster_key=None, week=None: (
            data.get_bench_analysis(roster_key, week)
        ),
        "standings": lambda week=None: data.get_standings(week),
        "player_summary": lambda player_key: data.get_player_summary(player_key),
        "player_weekly_log": lambda player_key, week_from=None, week_to=None: (
            data.get_player_weekly_log(
                player_key,
                week_from=week_from,
                week_to=week_to,
            )
        ),
        "season_leaders": (
            lambda week_from=None,
            week_to=None,
            position=None,
            roster_key=None,
            role=None,
            sort_by="total",
            limit=10: data.get_season_leaders(
                week_from=week_from,
                week_to=week_to,
                position=position,
                roster_key=roster_key,
                role=role,
                sort_by=sort_by,
                limit=limit,
            )
        ),
        "playoff_bracket": lambda bracket_type=None: (
            data.get_playoff_bracket(bracket_type)
        ),
        "team_playoff_path": lambda roster_key: (
            data.get_team_playoff_path(roster_key)
        ),
        "run_sql": lambda query, limit=200: data.run_sql(query, limit=limit),
    }


def _json_handler(handler: Callable[..., Any]) -> Callable[..., str]:
    def wrapped_handler(**kwargs: Any) -> str:
        return json.dumps(handler(**kwargs), default=str)

    return wrapped_handler
