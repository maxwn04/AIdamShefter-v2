# Phase 7: Datalayer Tool Integration

**Goal:** Adapt the 18 existing datalayer tools for the v2 runner's `ToolRegistry`.

**Files to create:**
- `reporter_v2/runner/tools/datalayer_tools.py`
- `reporter_v2/tests/test_datalayer_tools.py`

**Dependencies:** Phase 6 (ToolRegistry), Phase 1 (state)

---

## Design

The v1 `ResearchToolAdapter` wraps `SleeperLeagueData` methods and adds logging
+ soft limit nudges. V2 simplifies since logging and guardrails are handled by
the runner. The datalayer tools are registered as functions that call
`SleeperLeagueData` methods and return JSON strings.

## `reporter_v2/runner/tools/datalayer_tools.py`

```python
DATALAYER_TOOLS: list[dict[str, Any]] = [
    {
        "name": "league_snapshot",
        "method": "get_league_snapshot",
        "description": "Get league standings, games, and transactions for a week.",
        "parameters": {
            "type": "object",
            "properties": {
                "week": {"type": "integer", "description": "Week number"},
            },
        },
    },
    # ... 17 more entries matching the v1 tool list
]


def register_datalayer_tools(
    registry: ToolRegistry, data: SleeperLeagueData,
) -> None:
    """Register all 18 datalayer tools in the registry."""
    method_map = _build_method_map(data)

    for tool_def in DATALAYER_TOOLS:
        name = tool_def["name"]
        method = method_map[name]

        def make_handler(m):
            def handler(**kwargs: Any) -> str:
                result = m(**kwargs)
                return json.dumps(result, default=str)
            return handler

        spec = ToolSpec(
            name=name,
            description=tool_def["description"],
            parameters=tool_def["parameters"],
        )
        registry.register(name, make_handler(method), spec)


def _build_method_map(data: SleeperLeagueData) -> dict[str, Any]:
    return {
        "league_snapshot": data.get_league_snapshot,
        "week_games": data.get_week_games_with_players,
        "week_player_leaderboard": data.get_week_player_leaderboard,
        "season_leaders": data.get_season_leaders,
        "transactions": data.get_transactions,
        "team_dossier": data.get_team_dossier,
        "team_game": data.get_team_game_with_players,
        "team_schedule": data.get_team_schedule,
        "roster_current": data.get_roster_current,
        "roster_snapshot": data.get_roster_snapshot,
        "team_transactions": data.get_team_transactions,
        "bench_analysis": data.get_bench_analysis,
        "standings": data.get_standings,
        "player_summary": data.get_player_summary,
        "player_weekly_log": data.get_player_weekly_log,
        "playoff_bracket": data.get_playoff_bracket,
        "team_playoff_path": data.get_team_playoff_path,
        "run_sql": data.run_sql,
    }
```

## Tests

- `test_register_all_tools` -- verify all 18 tools are registered
- `test_datalayer_handler_returns_json` -- call a handler, verify valid JSON returned
- Test with a mock `SleeperLeagueData` or the existing test fixture if available
