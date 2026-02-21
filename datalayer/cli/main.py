"""CLI for the Sleeper data layer.

Commands mirror the tool definitions in datalayer.tools for consistency
between the interactive CLI and the agent API.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex

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

    app = subparsers.add_parser(
        "app", help="Load data and run interactive query shell."
    )
    app.add_argument(
        "--league-id",
        help="Sleeper league id (overrides SLEEPER_LEAGUE_ID).",
    )

    return parser


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


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
) -> tuple[dict[str, any], str | None]:
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

    result: dict[str, any] = {}
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
    if args.command == "app":
        return _run_app(args.league_id)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
