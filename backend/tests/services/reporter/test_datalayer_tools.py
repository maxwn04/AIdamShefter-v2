"""Tests for runner v2 datalayer tool adapters."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from backend.services.datalayer import (
    FrozenLeagueData,
    ReadyDataSnapshot,
    ResolvedRosterIdentity,
    RosterIdentityNotFound,
    SnapshotSeason,
)
from backend.services.reporter.generator import _get_league_metadata
from backend.tests.services.datalayer.test_frozen_query_runtime import (
    _without_volatile_player_state,
    ready_snapshot,
    v3_ready_snapshot,
)
from datalayer.tools import SLEEPER_TOOLS
from backend.services.reporter.runner.tools.datalayer_tools import (
    DATALAYER_TOOL_IMPLEMENTATION_VERSION,
    DATALAYER_TOOL_SPECS,
    register_datalayer_tools,
)
from backend.services.reporter.runner.tools.registry import ToolRegistry


EXPECTED_TOOL_NAMES = [
    "available_seasons",
    "league_history",
    "franchise_history",
    "league_snapshot",
    "week_games",
    "team_game",
    "week_player_leaderboard",
    "team_dossier",
    "team_schedule",
    "roster_at_cutoff",
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


class FakeFrozenLeagueData:
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

    def available_seasons(self) -> tuple[SnapshotSeason, ...]:
        self.calls.append(("available_seasons", (), {}))
        return (
            SnapshotSeason(
                competition_id=UUID(int=1),
                competition_season_id=UUID(int=2),
                sleeper_league_id="league-2024",
                season_year=2024,
                sequence_number=1,
                role="primary",
                through_week=8,
            ),
        )

    def get_league_history(self) -> dict[str, Any]:
        return self._record("get_league_history")

    def get_franchise_history(
        self,
        franchise_or_primary_roster: str | int,
    ) -> dict[str, Any]:
        return self._record(
            "get_franchise_history",
            franchise_or_primary_roster,
        )

    def get_league_snapshot(
        self,
        week: int | None = None,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        return self._record("get_league_snapshot", week, season=season)

    def get_week_games_with_players(
        self,
        week: int | None = None,
        *,
        season: int | None = None,
    ) -> list[dict[str, Any]]:
        return self._record(
            "get_week_games_with_players",
            week,
            season=season,
            result=[{"tool": "get_week_games_with_players", "week": week}],
        )

    def get_team_game_with_players(
        self,
        roster_key: Any,
        week: int | None = None,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        return self._record(
            "get_team_game_with_players",
            roster_key,
            week,
            season=season,
        )

    def get_week_player_leaderboard(
        self,
        week: int | None = None,
        limit: int = 10,
        *,
        season: int | None = None,
    ) -> list[dict[str, Any]]:
        return self._record(
            "get_week_player_leaderboard",
            week,
            limit,
            season=season,
            result=[],
        )

    def get_team_dossier(
        self,
        roster_key: Any,
        week: int | None = None,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        return self._record("get_team_dossier", roster_key, week, season=season)

    def get_team_schedule(
        self,
        roster_key: Any,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        return self._record("get_team_schedule", roster_key, season=season)

    def get_roster_at_cutoff(
        self,
        roster_key: Any,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        return self._record("get_roster_at_cutoff", roster_key, season=season)

    def get_roster_snapshot(
        self,
        roster_key: Any,
        week: int,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        return self._record("get_roster_snapshot", roster_key, week, season=season)

    def get_transactions(
        self,
        week_from: int,
        week_to: int,
        *,
        season: int | None = None,
    ) -> list[dict[str, Any]]:
        return self._record(
            "get_transactions",
            week_from,
            week_to,
            season=season,
            result=[],
        )

    def get_team_transactions(
        self,
        roster_key: Any,
        week_from: int,
        week_to: int,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        return self._record(
            "get_team_transactions",
            roster_key,
            week_from,
            week_to,
            season=season,
        )

    def get_bench_analysis(
        self,
        roster_key: Any = None,
        week: int | None = None,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        return self._record("get_bench_analysis", roster_key, week, season=season)

    def get_standings(
        self,
        week: int | None = None,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        return self._record("get_standings", week, season=season)

    def get_player_summary(self, player_key: Any) -> dict[str, Any]:
        return self._record("get_player_summary", player_key)

    def get_player_weekly_log(
        self,
        player_key: Any,
        week_from: int | None = None,
        week_to: int | None = None,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        return self._record(
            "get_player_weekly_log",
            player_key,
            week_from=week_from,
            week_to=week_to,
            season=season,
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
        season: int | None = None,
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
            season=season,
            result=[],
        )

    def get_playoff_bracket(
        self,
        bracket_type: str | None = None,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        return self._record("get_playoff_bracket", bracket_type, season=season)

    def get_team_playoff_path(
        self,
        roster_key: Any,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        return self._record("get_team_playoff_path", roster_key, season=season)

    def run_sql(self, query: str, *, limit: int = 200) -> dict[str, Any]:
        return self._record("run_sql", query, limit=limit)


def registered_registry() -> tuple[ToolRegistry, FakeFrozenLeagueData]:
    registry = ToolRegistry()
    data = FakeFrozenLeagueData()
    register_datalayer_tools(registry, data)  # type: ignore[arg-type]
    return registry, data


def decode(result: str) -> Any:
    return json.loads(result)


def test_reporter_owns_compatible_frozen_tool_specs() -> None:
    assert DATALAYER_TOOL_SPECS is not SLEEPER_TOOLS
    assert [
        spec["function"]["name"] for spec in DATALAYER_TOOL_SPECS
    ] == EXPECTED_TOOL_NAMES
    legacy_by_name = {spec["function"]["name"]: spec for spec in SLEEPER_TOOLS}
    for spec in DATALAYER_TOOL_SPECS:
        name = spec["function"]["name"]
        legacy_name = "roster_current" if name == "roster_at_cutoff" else name
        if legacy_name not in legacy_by_name:
            continue
        assert _without_season_and_descriptions(
            spec["function"]["parameters"]
        ) == (
            _without_descriptions(
                legacy_by_name[legacy_name]["function"]["parameters"]
            )
        )

    assert "roster_current" not in EXPECTED_TOOL_NAMES
    assert DATALAYER_TOOL_IMPLEMENTATION_VERSION == "2"


def test_only_season_scoped_tools_expose_optional_season_year() -> None:
    global_tools = {
        "available_seasons",
        "league_history",
        "franchise_history",
        "player_summary",
        "run_sql",
    }
    for spec in DATALAYER_TOOL_SPECS:
        function = spec["function"]
        properties = function["parameters"]["properties"]
        if function["name"] in global_tools:
            assert "season" not in properties
        else:
            assert properties["season"] == {
                "type": "integer",
                "minimum": 1900,
                "maximum": 9999,
                "description": (
                    "Four-digit season year. Omit for the primary season; use "
                    "available_seasons to discover valid years."
                ),
            }


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
    assert data.calls == [
        ("get_team_dossier", ("Team Taco", 8), {"season": None})
    ]


def test_optional_defaults_flow_through_handler_map() -> None:
    registry, data = registered_registry()
    handler = registry.get_handler("week_games")

    assert handler is not None
    result = decode(handler())

    assert result == [{"tool": "get_week_games_with_players", "week": None}]
    assert data.calls == [
        ("get_week_games_with_players", (None,), {"season": None})
    ]


def test_registered_handlers_do_not_share_late_bound_method() -> None:
    registry, data = registered_registry()
    team_handler = registry.get_handler("team_schedule")
    player_handler = registry.get_handler("player_summary")

    assert team_handler is not None
    assert player_handler is not None
    decode(team_handler(roster_key="Team Taco"))
    decode(player_handler(player_key="Patrick Mahomes"))

    assert data.calls == [
        ("get_team_schedule", ("Team Taco",), {"season": None}),
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
    with pytest.raises(TypeError):
        handler(query="SELECT * FROM games", params={"week": 2})


@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected_call"),
    [
        ("available_seasons", {}, ("available_seasons", (), {})),
        ("league_history", {}, ("get_league_history", (), {})),
        (
            "franchise_history",
            {"franchise_or_primary_roster": "Alpha"},
            ("get_franchise_history", ("Alpha",), {}),
        ),
        (
            "league_snapshot",
            {},
            ("get_league_snapshot", (None,), {"season": None}),
        ),
        (
            "week_games",
            {"week": 2},
            ("get_week_games_with_players", (2,), {"season": None}),
        ),
        (
            "team_game",
            {"roster_key": "Alpha", "week": 2},
            ("get_team_game_with_players", ("Alpha", 2), {"season": None}),
        ),
        (
            "week_player_leaderboard",
            {"week": 2, "limit": 3},
            ("get_week_player_leaderboard", (2, 3), {"season": None}),
        ),
        (
            "team_dossier",
            {"roster_key": "Alpha", "week": 2},
            ("get_team_dossier", ("Alpha", 2), {"season": None}),
        ),
        (
            "team_schedule",
            {"roster_key": "Alpha"},
            ("get_team_schedule", ("Alpha",), {"season": None}),
        ),
        (
            "roster_at_cutoff",
            {"roster_key": "Alpha"},
            ("get_roster_at_cutoff", ("Alpha",), {"season": None}),
        ),
        (
            "roster_snapshot",
            {"roster_key": "Alpha", "week": 1},
            ("get_roster_snapshot", ("Alpha", 1), {"season": None}),
        ),
        (
            "transactions",
            {"week_from": 1, "week_to": 2},
            ("get_transactions", (1, 2), {"season": None}),
        ),
        (
            "team_transactions",
            {"roster_key": "Alpha", "week_from": 1, "week_to": 2},
            ("get_team_transactions", ("Alpha", 1, 2), {"season": None}),
        ),
        (
            "bench_analysis",
            {},
            ("get_bench_analysis", (None, None), {"season": None}),
        ),
        ("standings", {}, ("get_standings", (None,), {"season": None})),
        (
            "player_summary",
            {"player_key": "p1"},
            ("get_player_summary", ("p1",), {}),
        ),
        (
            "player_weekly_log",
            {"player_key": "p1", "week_from": 1, "week_to": 2},
            (
                "get_player_weekly_log",
                ("p1",),
                {"week_from": 1, "week_to": 2, "season": None},
            ),
        ),
        (
            "season_leaders",
            {"position": "QB", "limit": 3},
            (
                "get_season_leaders",
                (),
                {
                    "week_from": None,
                    "week_to": None,
                    "position": "QB",
                    "roster_key": None,
                    "role": None,
                    "sort_by": "total",
                    "limit": 3,
                    "season": None,
                },
            ),
        ),
        (
            "playoff_bracket",
            {},
            ("get_playoff_bracket", (None,), {"season": None}),
        ),
        (
            "team_playoff_path",
            {"roster_key": "Alpha"},
            ("get_team_playoff_path", ("Alpha",), {"season": None}),
        ),
        (
            "run_sql",
            {"query": "SELECT * FROM games", "limit": 2},
            ("run_sql", ("SELECT * FROM games",), {"limit": 2}),
        ),
    ],
)
def test_every_tool_delegates_to_the_frozen_runtime(
    tool_name: str,
    arguments: dict[str, Any],
    expected_call: tuple[str, tuple[Any, ...], dict[str, Any]],
) -> None:
    registry, data = registered_registry()
    handler = registry.get_handler(tool_name)

    assert handler is not None
    decode(handler(**arguments))

    assert data.calls == [expected_call]


def test_all_tools_execute_against_a_real_frozen_artifact(
    ready_snapshot: ReadyDataSnapshot,
) -> None:
    calls = {
        "available_seasons": {},
        "league_history": {},
        "franchise_history": {"franchise_or_primary_roster": "Alpha"},
        "league_snapshot": {"week": 2},
        "week_games": {"week": 2},
        "team_game": {"roster_key": "Alpha", "week": 2},
        "week_player_leaderboard": {"week": 2, "limit": 3},
        "team_dossier": {"roster_key": "Alpha", "week": 2},
        "team_schedule": {"roster_key": "Alpha"},
        "roster_at_cutoff": {"roster_key": "Alpha"},
        "roster_snapshot": {"roster_key": "Alpha", "week": 1},
        "transactions": {"week_from": 1, "week_to": 2},
        "team_transactions": {
            "roster_key": "Alpha",
            "week_from": 1,
            "week_to": 2,
        },
        "bench_analysis": {"roster_key": "Alpha", "week": 2},
        "standings": {"week": 2},
        "player_summary": {"player_key": "p1"},
        "player_weekly_log": {
            "player_key": "p1",
            "week_from": 1,
            "week_to": 2,
        },
        "season_leaders": {
            "week_from": 1,
            "week_to": 2,
            "position": "QB",
            "roster_key": "Alpha",
            "role": "starter",
            "sort_by": "total",
            "limit": 3,
        },
        "playoff_bracket": {},
        "team_playoff_path": {"roster_key": "Alpha"},
        "run_sql": {
            "query": "SELECT week, matchup_id FROM games ORDER BY week",
            "limit": 2,
        },
    }

    with FrozenLeagueData.open(ready_snapshot) as data:
        registry = ToolRegistry()
        register_datalayer_tools(registry, data)
        results = {
            name: decode(registry.get_handler(name)(**arguments))  # type: ignore[misc]
            for name, arguments in calls.items()
        }

    golden_path = (
        Path(__file__).parents[4]
        / "datalayer"
        / "tests"
        / "characterization"
        / "golden"
        / "legacy_query_outputs.json"
    )
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    assert set(results) == set(EXPECTED_TOOL_NAMES)
    stable_results = _without_volatile_player_state(results)
    stable_golden = _without_volatile_player_state(golden)
    assert stable_results["week_games"] == stable_golden["week_games_with_players"]
    assert stable_results["team_game"] == stable_golden["team_game_with_players"]
    assert stable_results["team_schedule"] == stable_golden["team_schedule"]
    assert stable_results["roster_at_cutoff"] == stable_golden[
        "roster_current_by_name"
    ]
    assert results["run_sql"]["row_count"] == 2
    assert [season["season_year"] for season in results["available_seasons"]] == [
        2024
    ]
    assert len(results["league_history"]["seasons"]) == 1


def test_history_tools_and_explicit_season_execute_against_v3_artifact(
    v3_ready_snapshot: ReadyDataSnapshot,
) -> None:
    historical_calls = {
        "league_snapshot": {"week": 1, "season": 2025},
        "week_games": {"week": 1, "season": 2025},
        "team_game": {"roster_key": "1", "week": 1, "season": 2025},
        "week_player_leaderboard": {"week": 1, "limit": 3, "season": 2025},
        "team_dossier": {"roster_key": "1", "week": 1, "season": 2025},
        "team_schedule": {"roster_key": "1", "season": 2025},
        "roster_at_cutoff": {"roster_key": "1", "season": 2025},
        "roster_snapshot": {"roster_key": "1", "week": 1, "season": 2025},
        "transactions": {"week_from": 1, "week_to": 1, "season": 2025},
        "team_transactions": {
            "roster_key": "1",
            "week_from": 1,
            "week_to": 1,
            "season": 2025,
        },
        "bench_analysis": {"roster_key": "1", "week": 1, "season": 2025},
        "standings": {"week": 1, "season": 2025},
        "player_weekly_log": {
            "player_key": "p1",
            "week_from": 1,
            "week_to": 1,
            "season": 2025,
        },
        "season_leaders": {"week_from": 1, "week_to": 1, "season": 2025},
        "playoff_bracket": {"season": 2025},
        "team_playoff_path": {"roster_key": "1", "season": 2025},
    }
    with FrozenLeagueData.open(v3_ready_snapshot) as data:
        registry = ToolRegistry()
        register_datalayer_tools(registry, data)
        seasons = decode(registry.get_handler("available_seasons")())  # type: ignore[misc]
        league_history = decode(registry.get_handler("league_history")())  # type: ignore[misc]
        franchise_history = decode(
            registry.get_handler("franchise_history")(
                franchise_or_primary_roster="1"
            )  # type: ignore[misc]
        )
        results = {
            name: decode(registry.get_handler(name)(**arguments))  # type: ignore[misc]
            for name, arguments in historical_calls.items()
        }

    assert [season["season_year"] for season in seasons] == [2025, 2026]
    assert [season["season"] for season in league_history["seasons"]] == [
        2025,
        2026,
    ]
    assert franchise_history["found"] is True
    assert results["league_snapshot"]["league"]["name"] == "League 2025"
    assert set(results) == set(historical_calls)


def test_missing_entities_remain_safe_tool_results(
    ready_snapshot: ReadyDataSnapshot,
) -> None:
    with FrozenLeagueData.open(ready_snapshot) as data:
        registry = ToolRegistry()
        register_datalayer_tools(registry, data)
        missing = {
            "team": decode(
                registry.get_handler("team_dossier")(
                    roster_key="missing", week=2
                )  # type: ignore[misc]
            ),
            "roster": decode(
                registry.get_handler("roster_at_cutoff")(
                    roster_key="missing"
                )  # type: ignore[misc]
            ),
            "player": decode(
                registry.get_handler("player_summary")(
                    player_key="missing"
                )  # type: ignore[misc]
            ),
        }

    assert all(result["found"] is False for result in missing.values())


def test_generator_metadata_and_typed_roster_resolution_use_frozen_runtime(
    ready_snapshot: ReadyDataSnapshot,
) -> None:
    with FrozenLeagueData.open(ready_snapshot) as data:
        assert _get_league_metadata(data) == ("123", "Test League")
        for roster_key, roster_id, team_name in (
            ("Alpha", "1", "Alpha"),
            ("Alice", "1", "Alpha"),
            ("2", "2", "Beta"),
        ):
            result = data.resolve_roster_identity(roster_key)
            assert isinstance(result, ResolvedRosterIdentity)
            assert result.identity.sleeper_roster_id == roster_id
            assert result.identity.team_name == team_name

        missing = data.resolve_roster_identity("missing")
        assert isinstance(missing, RosterIdentityNotFound)
        assert missing.roster_key == "missing"


def test_reporter_adapter_and_datalayer_import_boundaries() -> None:
    root = Path(__file__).parents[4]
    adapter = (
        root
        / "backend"
        / "services"
        / "reporter"
        / "runner"
        / "tools"
        / "datalayer_tools.py"
    )
    adapter_imports = _imports(adapter)
    assert not any(
        name == "datalayer" or name.startswith("datalayer.")
        for name in adapter_imports
    )
    assert not any(name.startswith("backend.resources") for name in adapter_imports)
    assert not any(name.startswith("backend.database") for name in adapter_imports)

    datalayer_paths = [
        *(root / "datalayer").rglob("*.py"),
        *(root / "backend" / "services" / "datalayer").rglob("*.py"),
    ]
    reverse_imports = {
        name
        for path in datalayer_paths
        for name in _imports(path)
        if name == "backend.services.reporter"
        or name.startswith("backend.services.reporter.")
    }
    assert reverse_imports == set()


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


def _without_descriptions(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_descriptions(item)
            for key, item in value.items()
            if key != "description"
        }
    if isinstance(value, list):
        return [_without_descriptions(item) for item in value]
    return value


def _without_season_and_descriptions(value: Any) -> Any:
    stripped = _without_descriptions(value)
    if isinstance(stripped, dict):
        properties = stripped.get("properties")
        if isinstance(properties, dict):
            properties.pop("season", None)
    return stripped
