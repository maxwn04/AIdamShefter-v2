"""Tests for runner v2 datalayer tool adapters."""

from __future__ import annotations

import json
from typing import Any

from ai_gateway import ToolSpec
from datalayer.tools import SLEEPER_TOOLS
from reporter_v2.runner.tools.datalayer_tools import (
    DATALAYER_TOOL_SPECS,
    register_datalayer_tools,
)
from reporter_v2.runner.tools.registry import ToolRegistry


EXPECTED_TOOL_NAMES = [
    "league_snapshot",
    "week_games",
    "team_game",
    "week_player_leaderboard",
    "team_dossier",
    "team_schedule",
    "roster_current",
    "roster_snapshot",
    "transactions",
    "team_transactions",
    "bench_analysis",
    "standings",
    "player_summary",
    "player_weekly_log",
    "season_leaders",
    "playoff_bracket",
    "team_playoff_path",
    "run_sql",
]


class FakeSleeperLeagueData:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _record(
        self,
        name: str,
        *args: Any,
        result: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        self.calls.append((name, args, kwargs))
        return result if result is not None else {"tool": name}

    def get_league_snapshot(self, week: int | None = None) -> dict[str, Any]:
        return self._record("get_league_snapshot", week)

    def get_week_games_with_players(
        self, week: int | None = None
    ) -> list[dict[str, Any]]:
        return self._record(
            "get_week_games_with_players",
            week,
            result=[{"tool": "get_week_games_with_players", "week": week}],
        )

    def get_team_game_with_players(
        self, roster_key: Any, week: int | None = None
    ) -> dict[str, Any]:
        return self._record("get_team_game_with_players", roster_key, week)

    def get_week_player_leaderboard(
        self, week: int | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        return self._record("get_week_player_leaderboard", week, limit, result=[])

    def get_team_dossier(
        self, roster_key: Any, week: int | None = None
    ) -> dict[str, Any]:
        return self._record("get_team_dossier", roster_key, week)

    def get_team_schedule(self, roster_key: Any) -> dict[str, Any]:
        return self._record("get_team_schedule", roster_key)

    def get_roster_current(self, roster_key: Any) -> dict[str, Any]:
        return self._record("get_roster_current", roster_key)

    def get_roster_snapshot(self, roster_key: Any, week: int) -> dict[str, Any]:
        return self._record("get_roster_snapshot", roster_key, week)

    def get_transactions(self, week_from: int, week_to: int) -> list[dict[str, Any]]:
        return self._record("get_transactions", week_from, week_to, result=[])

    def get_team_transactions(
        self, roster_key: Any, week_from: int, week_to: int
    ) -> dict[str, Any]:
        return self._record("get_team_transactions", roster_key, week_from, week_to)

    def get_bench_analysis(
        self, roster_key: Any = None, week: int | None = None
    ) -> dict[str, Any]:
        return self._record("get_bench_analysis", roster_key, week)

    def get_standings(self, week: int | None = None) -> dict[str, Any]:
        return self._record("get_standings", week)

    def get_player_summary(self, player_key: Any) -> dict[str, Any]:
        return self._record("get_player_summary", player_key)

    def get_player_weekly_log(
        self,
        player_key: Any,
        week_from: int | None = None,
        week_to: int | None = None,
    ) -> dict[str, Any]:
        return self._record(
            "get_player_weekly_log",
            player_key,
            week_from=week_from,
            week_to=week_to,
        )

    def get_season_leaders(
        self,
        *,
        week_from: int | None = None,
        week_to: int | None = None,
        position: str | None = None,
        roster_key: Any = None,
        role: str | None = None,
        sort_by: str = "total",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return self._record(
            "get_season_leaders",
            week_from=week_from,
            week_to=week_to,
            position=position,
            roster_key=roster_key,
            role=role,
            sort_by=sort_by,
            limit=limit,
            result=[],
        )

    def get_playoff_bracket(
        self, bracket_type: str | None = None
    ) -> dict[str, Any]:
        return self._record("get_playoff_bracket", bracket_type)

    def get_team_playoff_path(self, roster_key: Any) -> dict[str, Any]:
        return self._record("get_team_playoff_path", roster_key)

    def run_sql(self, query: str, *, limit: int = 200) -> dict[str, Any]:
        return self._record("run_sql", query, limit=limit)


def registered_registry() -> tuple[ToolRegistry, FakeSleeperLeagueData]:
    registry = ToolRegistry()
    data = FakeSleeperLeagueData()
    register_datalayer_tools(registry, data)  # type: ignore[arg-type]
    return registry, data


def decode(result: str) -> Any:
    return json.loads(result)


def test_datalayer_tool_specs_come_from_sleeper_tools() -> None:
    assert DATALAYER_TOOL_SPECS == ToolSpec.from_openai_tools(SLEEPER_TOOLS)
    assert [spec.name for spec in DATALAYER_TOOL_SPECS] == EXPECTED_TOOL_NAMES


def test_register_all_datalayer_tools() -> None:
    registry, _ = registered_registry()

    assert registry.tool_names == EXPECTED_TOOL_NAMES
    assert registry.tool_specs == DATALAYER_TOOL_SPECS


def test_datalayer_handler_returns_json() -> None:
    registry, data = registered_registry()
    handler = registry.get_handler("team_dossier")

    assert handler is not None
    result = decode(handler(roster_key="Team Taco", week=8))

    assert result == {"tool": "get_team_dossier"}
    assert data.calls == [("get_team_dossier", ("Team Taco", 8), {})]


def test_optional_defaults_flow_through_v1_handler_map() -> None:
    registry, data = registered_registry()
    handler = registry.get_handler("week_games")

    assert handler is not None
    result = decode(handler())

    assert result == [{"tool": "get_week_games_with_players", "week": None}]
    assert data.calls == [("get_week_games_with_players", (None,), {})]


def test_registered_handlers_do_not_share_late_bound_method() -> None:
    registry, data = registered_registry()
    team_handler = registry.get_handler("team_schedule")
    player_handler = registry.get_handler("player_summary")

    assert team_handler is not None
    assert player_handler is not None
    decode(team_handler(roster_key="Team Taco"))
    decode(player_handler(player_key="Patrick Mahomes"))

    assert data.calls == [
        ("get_team_schedule", ("Team Taco",), {}),
        ("get_player_summary", ("Patrick Mahomes",), {}),
    ]


def test_run_sql_passes_default_and_explicit_limit() -> None:
    registry, data = registered_registry()
    handler = registry.get_handler("run_sql")

    assert handler is not None
    decode(handler(query="SELECT * FROM games"))
    decode(handler(query="SELECT * FROM games", limit=20))

    assert data.calls == [
        ("run_sql", ("SELECT * FROM games",), {"limit": 200}),
        ("run_sql", ("SELECT * FROM games",), {"limit": 20}),
    ]
