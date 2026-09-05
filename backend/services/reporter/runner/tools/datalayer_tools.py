"""Reporter-owned tools over one frozen league-data snapshot."""

from __future__ import annotations

from dataclasses import asdict
import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from backend.services.reporter.runner.models import ToolDef, ToolExecutionResult
from backend.services.reporter.runner.evidence import EvidenceCatalog
from backend.services.reporter.runner.tools.evidence_presentation import (
    evidence_page, public_subject_id, selected_records,
)
from backend.services.reporter.runner.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from backend.services.datalayer import FrozenLeagueData


DATALAYER_TOOL_IMPLEMENTATION_VERSION = "4"


def _week_property(description: str = "Week number (1-18).") -> dict[str, str]:
    return {"type": "integer", "description": description}


def _roster_property() -> dict[str, str]:
    return {
        "type": "string",
        "description": "Exact selected-season team/manager name, roster ID, or season_roster_id. Prefer returned roster_lookup arguments.",
    }


def _season_property() -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": 1900,
        "maximum": 9999,
        "description": (
            "Four-digit season year. Omit for the primary season; use "
            "available_seasons to discover valid years."
        ),
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
        "read_evidence",
        "Read executed evidence by source handle. Continue the overview with next_offset; request view=detail deliberately for the full catalog. Use returned refs in brief bindings.",
        {"source": {"type": "string"}, "offset": {"type": "integer", "minimum": 0},
         "view": {"type": "string", "enum": ["overview", "detail"], "description": "Default overview. Offsets are within the chosen view."},
         "limit": {"type": "integer", "minimum": 1, "maximum": 40}},
        ("source",),
    ),
    _tool(
        "available_seasons",
        "List every season available in this frozen snapshot, ordered from the "
        "oldest historical season to the primary season.",
        {},
    ),
    _tool(
        "league_history",
        "Get an oldest-to-primary summary of every included season with league "
        "metadata, cutoff, team count, and cutoff standings.",
        {},
    ),
    _tool(
        "franchise_history",
        "Resolve a franchise from a durable franchise UUID or a primary-season "
        "team, manager, or roster ID, then return its appearances across seasons.",
        {
            "franchise_or_primary_roster": {
                "type": "string",
                "description": (
                    "Durable franchise UUID, or a team name, manager name, or "
                    "roster_id from the primary season."
                ),
            }
        },
        ("franchise_or_primary_roster",),
    ),
    _tool(
        "league_snapshot",
        "Get league context, standings and head-to-head matchup results for a week. "
        "Use transactions for movement detail and team_game for player detail.",
        {
            "week": _week_property("Week number. Omit for snapshot cutoff."),
            "season": _season_property(),
        },
    ),
    _tool(
        "week_games",
        "Get every head-to-head matchup score and winner for a week. Use team_game for player-by-player detail.",
        {
            "week": _week_property("Week number. Omit for snapshot cutoff."),
            "season": _season_property(),
        },
    ),
    _tool(
        "team_game",
        "Get one team's game for a week with full player-by-player breakdowns.",
        {
            "roster_key": _roster_property(),
            "week": _week_property("Week number. Omit for snapshot cutoff."),
            "season": _season_property(),
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
            "season": _season_property(),
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
            "season": _season_property(),
        },
        ("roster_key",),
    ),
    _tool(
        "team_schedule",
        "Get a team's snapshot-bounded schedule with opponents, scores, results, "
        "and cumulative record.",
        {"roster_key": _roster_property(), "season": _season_property()},
        ("roster_key",),
    ),
    _tool(
        "roster_at_cutoff",
        "Get a team's roster composition at the selected snapshot cutoff, organized "
        "by role and position, plus draft picks owned.",
        {"roster_key": _roster_property(), "season": _season_property()},
        ("roster_key",),
    ),
    _tool(
        "roster_snapshot",
        "Get a team's roster and player scores during a specific week.",
        {
            "roster_key": _roster_property(),
            "week": _week_property("Week number to query."),
            "season": _season_property(),
        },
        ("roster_key", "week"),
    ),
    _tool(
        "transactions",
        "Get grouped trades, waivers, and free-agent pickups in a source week range. Check per-record status and occurred_at; week grouping does not establish postgame timing.",
        {
            "week_from": _week_property("Starting week (inclusive)."),
            "week_to": _week_property("Ending week (inclusive)."),
            "season": _season_property(),
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
            "season": _season_property(),
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
            "season": _season_property(),
        },
    ),
    _tool(
        "standings",
        "Get league standings, records, points, rank, and streaks for a week.",
        {
            "week": _week_property("Week number. Omit for snapshot cutoff."),
            "season": _season_property(),
        },
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
            "season": _season_property(),
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
            "season": _season_property(),
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
            },
            "season": _season_property(),
        },
    ),
    _tool(
        "team_playoff_path",
        "Get one team's playoff opponents, results, placement, and elimination or "
        "championship status.",
        {"roster_key": _roster_property(), "season": _season_property()},
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
                    "and snapshot_metadata. Version 3 also exposes "
                    "snapshot_seasons and roster_identities. In multi-season SQL, "
                    "scope joins by league_id and season-safe keys."
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
    adapter = _EvidenceAdapter(data, registry)
    for spec in DATALAYER_TOOL_SPECS:
        name = spec["function"]["name"]
        registry.register(
            name,
            adapter.read if name == "read_evidence" else adapter.wrap(name, handlers[name]),
            spec,
            DATALAYER_TOOL_IMPLEMENTATION_VERSION,
        )


def _create_tool_handlers(
    data: FrozenLeagueData,
) -> dict[str, Callable[..., Any]]:
    def player_weekly_log(
        player_key: Any,
        week_from: int | None = None,
        week_to: int | None = None,
        season: int | None = None,
    ) -> Any:
        return data.get_player_weekly_log(
            player_key,
            week_from=week_from,
            week_to=week_to,
            season=season,
        )

    def season_leaders(
        week_from: int | None = None,
        week_to: int | None = None,
        position: str | None = None,
        roster_key: Any = None,
        role: str | None = None,
        sort_by: str = "total",
        limit: int = 10,
        season: int | None = None,
    ) -> Any:
        return data.get_season_leaders(
            week_from=week_from,
            week_to=week_to,
            position=position,
            roster_key=roster_key,
            role=role,
            sort_by=sort_by,
            limit=limit,
            season=season,
        )

    return {
        "available_seasons": lambda: [
            season.model_dump(mode="json") for season in data.available_seasons()
        ],
        "league_history": lambda: data.get_league_history(),
        "franchise_history": lambda franchise_or_primary_roster: (
            data.get_franchise_history(franchise_or_primary_roster)
        ),
        "league_snapshot": lambda week=None, season=None: (
            data.get_league_snapshot(week, season=season)
        ),
        "week_games": lambda week=None, season=None: (
            data.get_week_games_with_players(week, season=season)
        ),
        "team_game": lambda roster_key, week=None, season=None: (
            data.get_team_game_with_players(roster_key, week, season=season)
        ),
        "week_player_leaderboard": lambda week=None, limit=10, season=None: (
            data.get_week_player_leaderboard(week, limit, season=season)
        ),
        "team_dossier": lambda roster_key, week=None, season=None: (
            data.get_team_dossier(roster_key, week, season=season)
        ),
        "team_schedule": lambda roster_key, season=None: (
            data.get_team_schedule(roster_key, season=season)
        ),
        "roster_at_cutoff": lambda roster_key, season=None: (
            data.get_roster_at_cutoff(roster_key, season=season)
        ),
        "roster_snapshot": lambda roster_key, week, season=None: (
            data.get_roster_snapshot(roster_key, week, season=season)
        ),
        "transactions": lambda week_from, week_to, season=None: (
            data.get_transactions(week_from, week_to, season=season)
        ),
        "team_transactions": lambda roster_key, week_from, week_to, season=None: (
            data.get_team_transactions(
                roster_key,
                week_from,
                week_to,
                season=season,
            )
        ),
        "bench_analysis": lambda roster_key=None, week=None, season=None: (
            data.get_bench_analysis(roster_key, week, season=season)
        ),
        "standings": lambda week=None, season=None: (
            data.get_standings(week, season=season)
        ),
        "player_summary": lambda player_key: data.get_player_summary(player_key),
        "player_weekly_log": player_weekly_log,
        "season_leaders": season_leaders,
        "playoff_bracket": lambda bracket_type=None, season=None: (
            data.get_playoff_bracket(bracket_type, season=season)
        ),
        "team_playoff_path": lambda roster_key, season=None: (
            data.get_team_playoff_path(roster_key, season=season)
        ),
        "run_sql": lambda query, limit=200: data.run_sql(query, limit=limit),
    }


class _EvidenceAdapter:
    def __init__(self, data: FrozenLeagueData, registry: ToolRegistry) -> None:
        self.data = data
        self.registry = registry
        self.seasons = [item.model_dump(mode="json") for item in data.available_seasons()]
        self.direct_catalog = EvidenceCatalog()
        self.direct_sequence = 0

    def read(self, source: str, offset: int = 0, limit: int = 40, view: str = "overview") -> ToolExecutionResult:
        ctx = self.registry.context
        catalog = ctx.evidence if ctx else self.direct_catalog
        records = catalog.records_for(source)
        if not records:
            return ToolExecutionResult(result={"found": False, "source": source, "error": "Unknown evidence source"})
        return ToolExecutionResult(result=_json_value(evidence_page(records, offset, limit, view=view)))

    def wrap(self, name: str, handler: Callable[..., Any]) -> Callable[..., ToolExecutionResult]:
        def execute(**kwargs: Any) -> ToolExecutionResult:
            ctx = self.registry.context
            if ctx:
                source = ctx.evidence_source()
                catalog = ctx.evidence
            else:
                self.direct_sequence += 1
                source = f"direct{self.direct_sequence}"
                catalog = self.direct_catalog
            raw = handler(**kwargs)
            seasons = self.seasons
            identities: dict[tuple[str, int | None], tuple[str | None, str | None]] = {}
            identity_audit: list[dict[str, Any]] = []

            def identity(subject: str, season: int | None) -> tuple[str | None, str | None]:
                key = (subject, season)
                if key not in identities:
                    # Legacy projection 2 deliberately has no durable identity map.
                    from backend.services.datalayer.query.identity import ResolvedRosterIdentity
                    resolution = self.data.resolve_roster_identity(subject, season=season)
                    if isinstance(resolution, ResolvedRosterIdentity):
                        identities[key] = (public_subject_id(str(resolution.identity.franchise_id)), resolution.identity.sleeper_roster_id)
                        identity_audit.append(resolution.model_dump(mode="json"))
                    else:
                        identities[key] = (None, None)
                return identities[key]

            warnings = self.data.completeness_warnings()
            records = selected_records(
                source, name, raw, kwargs, seasons, identity,
                snapshot_warnings=tuple(warning.model_dump(mode="json") for warning in warnings),
            )
            catalog.register(source, records)
            return ToolExecutionResult(
                result=_json_value(evidence_page(records)),
                metadata=_json_value({
                    "evidence_version": "1", "source": source, "raw_result": raw,
                    "records": [asdict(record) for record in records],
                    "snapshot_seasons": seasons, "identity_bindings": identity_audit,
                    "completeness_warnings": [warning.model_dump(mode="json") for warning in warnings],
                    "tool_call_id": str(ctx.current_tool_call_id) if ctx and ctx.current_tool_call_id else None,
                }),
            )
        return execute


def _json_value(value: Any) -> Any:
    """The durable recorder accepts JSON values, not dataclass tuples or UUIDs."""
    return json.loads(json.dumps(value, default=str))
