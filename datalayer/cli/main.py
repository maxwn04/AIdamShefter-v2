"""CLI for the Sleeper data layer.

Commands mirror the tool definitions in datalayer.tools for consistency
between the interactive CLI and the agent API.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import time
from typing import Any

from dotenv import load_dotenv

from datalayer.sleeper_data import SleeperLeagueData
from datalayer.tools import SLEEPER_TOOLS, create_tool_handlers


def _default_output_path(league_id: str) -> str:
    return os.path.join(".cache", "sleeper", f"{league_id}.sqlite")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sleeperdl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    load_export = subparsers.add_parser(
        "load-export", help="Load data and export SQLite file."
    )
    load_export.add_argument(
        "--league-id",
        help="Sleeper league id (overrides SLEEPER_LEAGUE_ID).",
    )
    load_export.add_argument(
        "--output",
        help="Output path for SQLite file.",
    )

    load = subparsers.add_parser(
        "load", help="Cache Sleeper data to a SQLite file for subsequent queries."
    )
    load.add_argument(
        "--league-id",
        help="Sleeper league id (overrides SLEEPER_LEAGUE_ID).",
    )
    load.add_argument(
        "--output",
        help="Output path for SQLite cache. Defaults to .cache/sleeper/<league_id>.sqlite.",
    )
    load.add_argument(
        "--refresh",
        action="store_true",
        help="Force a fresh Sleeper API load even if the cache is recent.",
    )

    snapshot = subparsers.add_parser(
        "snapshot", help="Load data and write a SQLite snapshot file."
    )
    snapshot.add_argument(
        "--league-id",
        help="Sleeper league id (overrides SLEEPER_LEAGUE_ID).",
    )
    snapshot.add_argument(
        "--output",
        required=True,
        help="Output path for SQLite snapshot.",
    )

    tools = subparsers.add_parser(
        "tools", help="Print available datalayer tools as JSON."
    )
    tools.set_defaults(command="tools")

    tool = subparsers.add_parser(
        "tool", help="Run one datalayer tool and print JSON."
    )
    tool.add_argument("tool_name", help="Tool name from `sleeperdl tools`.")
    tool.add_argument(
        "--args-json",
        default="{}",
        help="JSON object of tool arguments.",
    )
    tool.add_argument(
        "--snapshot",
        help="SQLite snapshot path. If omitted, data is loaded fresh.",
    )
    tool.add_argument(
        "--league-id",
        help="Sleeper league id for fresh loads (overrides SLEEPER_LEAGUE_ID).",
    )

    query = subparsers.add_parser(
        "query", help="Run one datalayer query from a cached SQLite snapshot."
    )
    query.add_argument("tool_name", help="Tool name from `sleeperdl tools`.")
    query.add_argument(
        "tool_args",
        nargs="*",
        help="Tool arguments in positional or key=value syntax.",
    )
    query.add_argument(
        "--snapshot",
        help="SQLite snapshot path. Defaults to .cache/sleeper/<league_id>.sqlite.",
    )
    query.add_argument(
        "--league-id",
        help="Sleeper league id (overrides SLEEPER_LEAGUE_ID).",
    )
    query.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh the cache before running the query.",
    )

    app = subparsers.add_parser(
        "app", help="Load data and run interactive query shell."
    )
    app.add_argument(
        "--league-id",
        help="Sleeper league id (overrides SLEEPER_LEAGUE_ID).",
    )

    return parser


def _print_error(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _get_tool_def(tool_name: str) -> dict[str, Any] | None:
    for tool in SLEEPER_TOOLS:
        func = tool["function"]
        if func["name"] == tool_name:
            return func
    return None


def _parse_json_params(raw: str) -> tuple[dict[str, Any], str | None]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"--args-json must be valid JSON: {exc.msg}"

    if not isinstance(parsed, dict):
        return {}, "--args-json must decode to a JSON object"

    return parsed, None


def _validate_tool_params(
    tool_name: str, params: dict[str, Any]
) -> tuple[dict[str, Any], str | None]:
    tool_def = _get_tool_def(tool_name)
    if tool_def is None:
        names = ", ".join(sorted(tool["function"]["name"] for tool in SLEEPER_TOOLS))
        return {}, f"Unknown tool: {tool_name}. Available tools: {names}"

    properties = tool_def["parameters"].get("properties", {})
    required = set(tool_def["parameters"].get("required", []))
    provided = set(params)

    unknown = provided - set(properties)
    if unknown:
        return {}, f"Unknown parameter(s): {', '.join(sorted(unknown))}"

    missing = required - provided
    if missing:
        return {}, f"Missing required parameter(s): {', '.join(sorted(missing))}"

    validated = dict(params)
    for key, value in validated.items():
        ptype = properties[key].get("type")
        if ptype == "integer" and value is not None and not isinstance(value, int):
            try:
                validated[key] = int(value)
            except (TypeError, ValueError):
                return {}, f"Parameter '{key}' must be an integer"

    return validated, None


def _load_data_for_tool(
    *, snapshot: str | None, league_id: str | None
) -> SleeperLeagueData:
    if snapshot:
        return SleeperLeagueData.from_file(snapshot)

    data = SleeperLeagueData(league_id=league_id)
    data.load()
    return data


CACHE_TTL_SECONDS = 60 * 60


def _is_recent_file(path: str, ttl_seconds: int = CACHE_TTL_SECONDS) -> bool:
    if not os.path.exists(path):
        return False
    age_seconds = time.time() - os.path.getmtime(path)
    return age_seconds < ttl_seconds


def _resolve_cache_path(league_id: str | None, output_path: str | None = None) -> str:
    if output_path:
        return output_path
    probe = SleeperLeagueData(league_id=league_id)
    return _default_output_path(probe.league_id)


def _refresh_cache(league_id: str | None, output_path: str) -> str:
    data = SleeperLeagueData(league_id=league_id)
    data.load()
    return data.save_to_file(output_path)


def _run_load_command(
    *, league_id: str | None, output_path: str | None, refresh: bool = False
) -> int:
    try:
        resolved_output = _resolve_cache_path(league_id, output_path)
        if not refresh and _is_recent_file(resolved_output):
            print(resolved_output)
            return 0

        saved_path = _refresh_cache(league_id, resolved_output)
        print(saved_path)
        return 0
    except Exception as exc:
        _print_error(str(exc))
        return 1


def _run_query_command(
    tool_name: str,
    *,
    tool_args: list[str],
    snapshot: str | None,
    league_id: str | None,
    refresh: bool = False,
) -> int:
    try:
        resolved_snapshot = snapshot or _resolve_cache_path(league_id)
        if refresh or not os.path.exists(resolved_snapshot):
            _refresh_cache(league_id, resolved_snapshot)
    except Exception as exc:
        _print_error(str(exc))
        return 1

    params, error = _parse_tool_args(tool_args, tool_name)
    if error:
        _print_error(error)
        return 2

    args_json = json.dumps(params)
    return _run_tool_command(
        tool_name,
        args_json=args_json,
        snapshot=resolved_snapshot,
        league_id=league_id,
    )


def _run_tool_command(
    tool_name: str,
    *,
    args_json: str,
    snapshot: str | None,
    league_id: str | None,
) -> int:
    params, error = _parse_json_params(args_json)
    if error:
        _print_error(error)
        return 2

    params, error = _validate_tool_params(tool_name, params)
    if error:
        _print_error(error)
        return 2

    try:
        data = _load_data_for_tool(snapshot=snapshot, league_id=league_id)
    except Exception as exc:
        _print_error(str(exc))
        return 1

    handlers = create_tool_handlers(data)
    try:
        result = handlers[tool_name](**params)
    except Exception as exc:
        _print_error(str(exc))
        return 1

    _print_json(result)
    return 0


def _build_tool_help() -> str:
    """Build help text from tool definitions."""
    lines = ["", "Available tools (commands):"]
    for tool in SLEEPER_TOOLS:
        func = tool["function"]
        name = func["name"]
        desc = func["description"].split(".")[0]  # First sentence only
        params = func["parameters"]["properties"]
        required = func["parameters"].get("required", [])

        # Build parameter hint
        param_parts = []
        for pname, pdef in params.items():
            ptype = pdef.get("type", "string")
            if pname in required:
                param_parts.append(f"<{pname}:{ptype}>")
            else:
                param_parts.append(f"[{pname}:{ptype}]")

        param_str = " ".join(param_parts) if param_parts else ""
        lines.append(f"  {name} {param_str}")
        lines.append(f"      {desc}")

    lines.extend([
        "",
        "Other commands:",
        "  save [output_path]  - Export SQLite file",
        "  tools               - Show this help",
        "  help                - Show this help",
        "  exit | quit         - Exit the app",
        "",
        "Parameters can be passed positionally or as key=value pairs:",
        "  team_dossier Schefter",
        "  team_dossier roster_key=Schefter week=5",
        '  player_summary player_key="Patrick Mahomes"',
        "",
    ])
    return "\n".join(lines)


def _parse_tool_args(
    args: list[str], tool_name: str
) -> tuple[dict[str, Any], str | None]:
    """Parse command arguments into tool parameters.

    Supports both positional and key=value syntax.

    Returns:
        (params_dict, error_message)
    """
    # Find the tool definition
    tool_def = None
    for tool in SLEEPER_TOOLS:
        if tool["function"]["name"] == tool_name:
            tool_def = tool["function"]
            break

    if not tool_def:
        return {}, f"Unknown tool: {tool_name}"

    properties = tool_def["parameters"]["properties"]
    required = tool_def["parameters"].get("required", [])
    param_names = list(properties.keys())

    result: dict[str, Any] = {}
    positional_idx = 0

    for arg in args:
        if "=" in arg:
            # Key=value syntax
            key, value = arg.split("=", 1)
            if key not in properties:
                return {}, f"Unknown parameter: {key}"
            result[key] = value
        else:
            # Positional argument
            if positional_idx >= len(param_names):
                return {}, f"Too many arguments"
            key = param_names[positional_idx]
            result[key] = arg
            positional_idx += 1

    # Convert types based on schema
    for key, value in result.items():
        if key in properties:
            ptype = properties[key].get("type")
            if ptype == "integer":
                try:
                    result[key] = int(value)
                except ValueError:
                    return {}, f"Parameter '{key}' must be an integer"

    # Check required parameters
    for req in required:
        if req not in result:
            return {}, f"Missing required parameter: {req}"

    return result, None


def _run_app(league_id: str | None) -> int:
    data = SleeperLeagueData(league_id=league_id)
    print("Loading data...")
    data.load()
    print(f"Loaded league: {data.league_id}")

    handlers = create_tool_handlers(data)
    help_text = _build_tool_help()
    print(help_text)

    while True:
        try:
            raw = input("sleeperdl> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("")
            return 0

        if not raw:
            continue
        if raw in {"exit", "quit"}:
            return 0
        if raw in {"help", "tools"}:
            print(help_text)
            continue

        # Parse command - use shlex to handle quoted strings
        try:
            parts = shlex.split(raw)
        except ValueError as e:
            print(f"Parse error: {e}")
            continue

        command = parts[0]
        args = parts[1:]

        # Handle save command specially
        if command == "save":
            output_path = args[0] if args else _default_output_path(data.league_id)
            if os.path.exists(output_path):
                confirm = (
                    input(f"{output_path} exists. Overwrite? [y/N] ").strip().lower()
                )
                if confirm not in {"y", "yes"}:
                    print("Save cancelled.")
                    continue
            try:
                saved_path = data.save_to_file(output_path)
                print(f"Saved SQLite snapshot to {saved_path}.")
            except Exception as exc:
                print(f"Error: {exc}")
            continue

        # Check if it's a valid tool
        if command not in handlers:
            print(f"Unknown command: {command}")
            print("Type 'tools' to see available commands.")
            continue

        # Parse arguments for the tool
        params, error = _parse_tool_args(args, command)
        if error:
            print(f"Error: {error}")
            # Show usage for this tool
            for tool in SLEEPER_TOOLS:
                if tool["function"]["name"] == command:
                    props = tool["function"]["parameters"]["properties"]
                    req = tool["function"]["parameters"].get("required", [])
                    usage_parts = [command]
                    for pname in props:
                        if pname in req:
                            usage_parts.append(f"<{pname}>")
                        else:
                            usage_parts.append(f"[{pname}]")
                    print(f"Usage: {' '.join(usage_parts)}")
                    break
            continue

        # Execute the tool
        try:
            result = handlers[command](**params)
            _print_json(result)
        except Exception as exc:
            print(f"Error: {exc}")

    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "load-export":
        data = SleeperLeagueData(league_id=args.league_id)
        data.load()
        output_path = args.output or _default_output_path(data.league_id)
        saved_path = data.save_to_file(output_path)
        print(saved_path)
        return 0
    if args.command == "load":
        return _run_load_command(
            league_id=args.league_id,
            output_path=args.output,
            refresh=args.refresh,
        )
    if args.command == "snapshot":
        data = SleeperLeagueData(league_id=args.league_id)
        data.load()
        saved_path = data.save_to_file(args.output)
        print(saved_path)
        return 0
    if args.command == "tools":
        _print_json(SLEEPER_TOOLS)
        return 0
    if args.command == "tool":
        return _run_tool_command(
            args.tool_name,
            args_json=args.args_json,
            snapshot=args.snapshot,
            league_id=args.league_id,
        )
    if args.command == "query":
        return _run_query_command(
            args.tool_name,
            tool_args=args.tool_args,
            snapshot=args.snapshot,
            league_id=args.league_id,
            refresh=args.refresh,
        )
    if args.command == "app":
        return _run_app(args.league_id)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
