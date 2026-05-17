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

from datalayer.context_store import ContextStore
from datalayer.context_tools import create_context_tool_handlers
from datalayer.sleeper_data import SleeperLeagueData
from datalayer.sleeper_data.queries._resolvers import resolve_roster_id
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

    def add_context_parser(command_name: str) -> None:
        context = subparsers.add_parser(
            command_name, help="Read or update persistent reporter storyline context."
        )
        context_subparsers = context.add_subparsers(
            dest="context_command", required=True
        )

        def add_context_scope_args(subparser: argparse.ArgumentParser) -> None:
            subparser.add_argument(
                "--snapshot",
                required=True,
                help="SQLite snapshot path used to scope league, season, week, and team resolution.",
            )
            subparser.add_argument(
                "--db-path",
                default=os.path.join(".data", "context.db"),
                help="Persistent context database path.",
            )
            subparser.add_argument(
                "--week",
                type=int,
                help="Week to record for writes. Defaults to the snapshot effective week.",
            )

        full = context_subparsers.add_parser(
            "full", help="Print storylines, team context, and league notes."
        )
        add_context_scope_args(full)

        get = context_subparsers.add_parser(
            "get", help="Compatibility alias for `full`."
        )
        add_context_scope_args(get)

        storylines = context_subparsers.add_parser(
            "storylines", help="Print active and stale storylines."
        )
        add_context_scope_args(storylines)
        storylines.add_argument("--include-resolved", action="store_true")

        enriched = context_subparsers.add_parser(
            "enriched", help="Print storylines with history and persisted facts."
        )
        add_context_scope_args(enriched)
        enriched.add_argument("storyline_ids", nargs="+")

        teams = context_subparsers.add_parser("teams", help="Print all team context.")
        add_context_scope_args(teams)

        team = context_subparsers.add_parser("team", help="Print one team's context.")
        add_context_scope_args(team)
        team.add_argument("roster_key")

        league = context_subparsers.add_parser(
            "league", help="Print league-level context notes."
        )
        add_context_scope_args(league)

        save_storyline = context_subparsers.add_parser(
            "save-storyline", help="Create or update a persistent storyline."
        )
        add_context_scope_args(save_storyline)
        save_storyline.add_argument("--id", required=True)
        save_storyline.add_argument("--headline", required=True)
        save_storyline.add_argument("--summary", required=True)
        save_storyline.add_argument(
            "--status", choices=["active", "resolved"], default="active"
        )
        save_storyline.add_argument("--priority", type=int, default=2)
        save_storyline.add_argument(
            "--tags",
            default="",
            help="Comma-separated tags or a JSON string array.",
        )
        save_storyline.add_argument(
            "--team-keys",
            "--teams",
            default="",
            help="Comma-separated team names/manager names/roster ids or a JSON string array.",
        )

        for save_team_name in ("save-team", "save-team-context"):
            save_team = context_subparsers.add_parser(
                save_team_name, help="Create or update a team context note."
            )
            add_context_scope_args(save_team)
            save_team.add_argument("--roster-key", required=True)
            save_team.add_argument("--narrative", required=True)
            save_team.add_argument(
                "--outlook",
                choices=["rebuilding", "contending", "middling", "surging", "fading"],
            )

        save_note = context_subparsers.add_parser(
            "save-league-note", help="Create or update a league-level context note."
        )
        add_context_scope_args(save_note)
        save_note.add_argument("--key", required=True)
        save_note.add_argument("--value", required=True)

        persist_facts = context_subparsers.add_parser(
            "persist-facts", help="Persist verified facts for a storyline."
        )
        add_context_scope_args(persist_facts)
        persist_facts.add_argument("--storyline-id", required=True)
        persist_facts.add_argument(
            "--facts-json",
            required=True,
            help="JSON array of ReportBrief-style fact objects.",
        )

        stale = context_subparsers.add_parser(
            "mark-stale", help="Mark old active storylines as stale."
        )
        add_context_scope_args(stale)
        stale.add_argument("--weeks-threshold", type=int, default=4)

    add_context_parser("context")
    add_context_parser("memory")

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


def _parse_list_arg(value: str) -> list[str]:
    if not value:
        return []
    stripped = value.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        parsed = json.loads(stripped)
        if not isinstance(parsed, list) or not all(
            isinstance(item, str) for item in parsed
        ):
            raise ValueError("List argument JSON must be an array of strings")
        return parsed
    return [part.strip() for part in stripped.split(",") if part.strip()]


def _context_scope(
    snapshot: str,
) -> tuple[SleeperLeagueData, str, str, int]:
    data = SleeperLeagueData.from_file(snapshot)
    season_result = data.run_sql("SELECT season FROM leagues LIMIT 1")
    if not season_result["rows"]:
        raise ValueError(f"Snapshot has no season row: {snapshot}")
    season = str(season_result["rows"][0][0])
    if data.effective_week is None:
        raise ValueError(f"Snapshot has no effective week: {snapshot}")
    return data, data.league_id, season, int(data.effective_week)


def _resolve_context_roster_id(data: SleeperLeagueData, roster_key: str) -> int | None:
    if not data._query_conn:
        return None
    result = resolve_roster_id(data._query_conn, data.league_id, roster_key)
    if result.get("found"):
        return int(result["roster_id"])
    return None


def _parse_facts_arg(raw: str) -> list[dict[str, Any]]:
    parsed = json.loads(raw)
    if not isinstance(parsed, list) or not all(
        isinstance(item, dict) for item in parsed
    ):
        raise ValueError("--facts-json must be a JSON array of objects")
    return parsed


def _run_context_command(args: argparse.Namespace) -> int:
    try:
        data, league_id, season, snapshot_week = _context_scope(args.snapshot)
        week = args.week or snapshot_week
        store = ContextStore(args.db_path, league_id=league_id, season=season)
        resolve_fn = None
        if data._query_conn:
            resolve_fn = lambda key: resolve_roster_id(
                data._query_conn, data.league_id, key
            )
        handlers = create_context_tool_handlers(
            store, week=week, resolve_roster_fn=resolve_fn
        )

        if args.context_command in {"full", "get"}:
            context = store.get_full_context()
            _print_json(
                {
                    "has_previous_context": bool(
                        context["storylines"]
                        or context["team_context"]
                        or context["league_context"]
                    ),
                    **context,
                }
            )
            return 0

        if args.context_command == "storylines":
            _print_json(store.get_storylines(include_resolved=args.include_resolved))
            return 0

        if args.context_command == "enriched":
            _print_json(store.get_enriched_storylines(args.storyline_ids))
            return 0

        if args.context_command == "teams":
            _print_json(store.get_all_team_context())
            return 0

        if args.context_command == "team":
            roster_id = _resolve_context_roster_id(data, args.roster_key)
            if roster_id is None:
                _print_json(
                    {
                        "found": False,
                        "error": f"Could not resolve team: {args.roster_key}",
                    }
                )
                return 0
            team_context = store.get_team_context(roster_id)
            if team_context is None:
                _print_json({"found": False, "roster_id": roster_id})
                return 0
            _print_json({"found": True, **team_context})
            return 0

        if args.context_command == "league":
            _print_json(store.get_league_context())
            return 0

        if args.context_command == "save-storyline":
            result = handlers["save_storyline"](
                id=args.id,
                headline=args.headline,
                summary=args.summary,
                status=args.status,
                priority=args.priority,
                tags=_parse_list_arg(args.tags),
                team_keys=_parse_list_arg(args.team_keys),
            )
            _print_json(result)
            return 0

        if args.context_command in {"save-team", "save-team-context"}:
            result = handlers["save_team_context"](
                roster_key=args.roster_key,
                narrative=args.narrative,
                outlook=args.outlook,
            )
            _print_json(result)
            return 0

        if args.context_command == "save-league-note":
            result = handlers["save_league_note"](key=args.key, value=args.value)
            _print_json(result)
            return 0

        if args.context_command == "persist-facts":
            count = store.persist_facts(
                _parse_facts_arg(args.facts_json),
                args.storyline_id,
                week=week,
            )
            _print_json({"inserted": count, "storyline_id": args.storyline_id})
            return 0

        if args.context_command == "mark-stale":
            _print_json(
                {
                    "stale_count": store.mark_stale(
                        current_week=week,
                        weeks_threshold=args.weeks_threshold,
                    )
                }
            )
            return 0
    except Exception as exc:
        _print_error(str(exc))
        return 1

    _print_error(f"Unknown context command: {args.context_command}")
    return 2


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
    if args.command in {"context", "memory"}:
        return _run_context_command(args)
    if args.command == "app":
        return _run_app(args.league_id)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
