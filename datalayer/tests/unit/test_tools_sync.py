"""Tests that tool definitions stay in sync with SleeperLeagueData query methods.

These tests catch drift between:
- SleeperLeagueData public query methods
- SLEEPER_TOOLS definitions (OpenAI function-calling format)
- create_tool_handlers() handler map
"""

import inspect

import pytest

from datalayer.sleeper_data import SleeperLeagueData
from datalayer.tools import SLEEPER_TOOLS, create_tool_handlers


# Methods on SleeperLeagueData that are NOT tools (infrastructure, not queries)
NON_TOOL_METHODS = {"load", "save_to_file"}

# Methods that were consolidated into other tools and have no direct tool definition
CONSOLIDATED_METHODS = {
    "get_week_games",           # subsumed by week_games (maps to get_week_games_with_players)
    "get_team_game",            # subsumed by team_game (maps to get_team_game_with_players)
    "get_week_transactions",    # use transactions(week, week)
    "get_team_week_transactions",  # use team_transactions(roster, week, week)
}

# Tool names that map to a differently-named method (tool_name -> method_name)
TOOL_TO_METHOD = {
    "week_games": "get_week_games_with_players",
    "team_game": "get_team_game_with_players",
}


def _get_query_methods() -> dict[str, inspect.Signature]:
    """Return public query methods on SleeperLeagueData (name -> signature)."""
    methods = {}
    for name, method in inspect.getmembers(SleeperLeagueData, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        if name in NON_TOOL_METHODS:
            continue
        methods[name] = inspect.signature(method)
    return methods


def _get_tool_names() -> set[str]:
    """Return set of tool names from SLEEPER_TOOLS."""
    return {tool["function"]["name"] for tool in SLEEPER_TOOLS}


def _get_tool_by_name(name: str) -> dict | None:
    """Look up a tool definition by name."""
    for tool in SLEEPER_TOOLS:
        if tool["function"]["name"] == name:
            return tool["function"]
    return None


def _tool_to_method_name(tool_name: str) -> str:
    """Map a tool name to its corresponding SleeperLeagueData method name."""
    if tool_name in TOOL_TO_METHOD:
        return TOOL_TO_METHOD[tool_name]
    return f"get_{tool_name}" if tool_name != "run_sql" else "run_sql"


class TestToolsCoverAllQueryMethods:
    """Every public query method on SleeperLeagueData should have a tool definition."""

    def test_all_query_methods_have_tool_definitions(self):
        query_methods = _get_query_methods()
        tool_names = _get_tool_names()

        # Map tool names to the method names they cover
        covered_methods = {_tool_to_method_name(t) for t in tool_names}

        # Methods not covered by any tool and not in the consolidated set
        missing = set(query_methods.keys()) - covered_methods - CONSOLIDATED_METHODS
        assert missing == set(), (
            f"Query methods missing from SLEEPER_TOOLS: {sorted(missing)}. "
            "Add tool definitions for these methods in datalayer/tools.py."
        )

    def test_no_orphan_tool_definitions(self):
        """Every tool definition should map to a real query method."""
        query_methods = _get_query_methods()
        tool_names = _get_tool_names()

        orphans = set()
        for tool_name in tool_names:
            method_name = _tool_to_method_name(tool_name)
            if method_name not in query_methods:
                orphans.add(tool_name)

        assert orphans == set(), (
            f"SLEEPER_TOOLS references non-existent methods: {sorted(orphans)}. "
            "Remove these tool definitions or add the methods to SleeperLeagueData."
        )


class TestToolParametersMatchSignatures:
    """Tool parameter names and required/optional status should match method signatures."""

    @pytest.fixture
    def query_methods(self):
        return _get_query_methods()

    def test_tool_parameters_match_method_signatures(self, query_methods):
        mismatches = []

        for tool in SLEEPER_TOOLS:
            func_def = tool["function"]
            tool_name = func_def["name"]
            method_name = _tool_to_method_name(tool_name)

            if method_name not in query_methods:
                continue  # Caught by orphan test

            sig = query_methods[method_name]
            # Skip 'self' parameter
            method_params = {
                name: param
                for name, param in sig.parameters.items()
                if name != "self"
            }

            tool_props = func_def["parameters"].get("properties", {})
            tool_required = set(func_def["parameters"].get("required", []))

            # Check tool params are a subset of method params
            tool_param_names = set(tool_props.keys())
            method_param_names = set(method_params.keys())

            extra_in_tool = tool_param_names - method_param_names
            if extra_in_tool:
                mismatches.append(
                    f"{tool_name}: tool has params not in method: {extra_in_tool}"
                )

            # Check required/optional alignment
            for param_name in tool_param_names & method_param_names:
                method_param = method_params[param_name]
                has_default = method_param.default is not inspect.Parameter.empty
                is_tool_required = param_name in tool_required

                if is_tool_required and has_default:
                    mismatches.append(
                        f"{tool_name}.{param_name}: tool says required but method has default"
                    )
                if not is_tool_required and not has_default:
                    mismatches.append(
                        f"{tool_name}.{param_name}: tool says optional but method has no default"
                    )

        assert mismatches == [], (
            "Tool parameter mismatches:\n" + "\n".join(f"  - {m}" for m in mismatches)
        )


class TestToolHandlersCoverAllTools:
    """create_tool_handlers() should return a handler for every tool in SLEEPER_TOOLS."""

    def test_tool_handlers_cover_all_tools(self):
        # We can't call create_tool_handlers without a loaded instance,
        # but we can inspect the function source to check handler names.
        # Instead, use a mock-like approach: create a minimal stub.
        tool_names = _get_tool_names()

        # Inspect the source of create_tool_handlers to extract handler keys
        source = inspect.getsource(create_tool_handlers)

        missing_handlers = []
        for name in tool_names:
            # Check that the tool name appears as a key in the handler dict
            if f'"{name}"' not in source:
                missing_handlers.append(name)

        assert missing_handlers == [], (
            f"create_tool_handlers() missing handlers for: {sorted(missing_handlers)}. "
            "Add handler entries in datalayer/tools.py create_tool_handlers()."
        )
