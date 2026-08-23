"""Tests for runner v2 datalayer tool adapters."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from backend.services.datalayer import (
    FrozenLeagueData,
    ReadyDataSnapshot,
    ResolvedRosterIdentity,
    RosterIdentityNotFound,
)
from backend.services.reporter.generator import _get_league_metadata
from backend.tests.services.datalayer.test_frozen_query_runtime import (
    _without_volatile_player_state,
    ready_snapshot,
)
from datalayer.tools import SLEEPER_TOOLS
from backend.services.reporter.runner.tools.datalayer_tools import (
    DATALAYER_TOOL_SPECS,
    register_datalayer_tools,
)
from backend.services.reporter.runner.tools.registry import ToolRegistry


EXPECTED_TOOL_NAMES = [
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

    def get_roster_at_cutoff(self, roster_key: Any) -> dict[str, Any]:
        return self._record("get_roster_at_cutoff", roster_key)

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
        assert _without_descriptions(spec["function"]["parameters"]) == (
            _without_descriptions(
                legacy_by_name[legacy_name]["function"]["parameters"]
            )
        )

    assert "roster_current" not in EXPECTED_TOOL_NAMES


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
    with pytest.raises(TypeError):
        handler(query="SELECT * FROM games", params={"week": 2})


@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected_call"),
    [
        ("league_snapshot", {}, ("get_league_snapshot", (None,), {})),
        ("week_games", {"week": 2}, ("get_week_games_with_players", (2,), {})),
        (
            "team_game",
            {"roster_key": "Alpha", "week": 2},
            ("get_team_game_with_players", ("Alpha", 2), {}),
        ),
        (
            "week_player_leaderboard",
            {"week": 2, "limit": 3},
            ("get_week_player_leaderboard", (2, 3), {}),
        ),
        (
            "team_dossier",
            {"roster_key": "Alpha", "week": 2},
            ("get_team_dossier", ("Alpha", 2), {}),
        ),
        (
            "team_schedule",
            {"roster_key": "Alpha"},
            ("get_team_schedule", ("Alpha",), {}),
        ),
        (
            "roster_at_cutoff",
            {"roster_key": "Alpha"},
            ("get_roster_at_cutoff", ("Alpha",), {}),
        ),
        (
            "roster_snapshot",
            {"roster_key": "Alpha", "week": 1},
            ("get_roster_snapshot", ("Alpha", 1), {}),
        ),
        (
            "transactions",
            {"week_from": 1, "week_to": 2},
            ("get_transactions", (1, 2), {}),
        ),
        (
            "team_transactions",
            {"roster_key": "Alpha", "week_from": 1, "week_to": 2},
            ("get_team_transactions", ("Alpha", 1, 2), {}),
        ),
        (
            "bench_analysis",
            {},
            ("get_bench_analysis", (None, None), {}),
        ),
        ("standings", {}, ("get_standings", (None,), {})),
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
                {"week_from": 1, "week_to": 2},
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
                },
            ),
        ),
        (
            "playoff_bracket",
            {},
            ("get_playoff_bracket", (None,), {}),
        ),
        (
            "team_playoff_path",
            {"roster_key": "Alpha"},
            ("get_team_playoff_path", ("Alpha",), {}),
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
