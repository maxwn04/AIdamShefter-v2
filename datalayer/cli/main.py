"""Barebones CLI for the Sleeper data layer."""

from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv

from datalayer.sleeper_data import SleeperLeagueData


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


def _app_help() -> None:
    print(
        "\n".join(
            [
                "Commands:",
                "  snapshot [week]",
                "  games [--week <week>] [--roster <roster_id or name>] [--include-players]",
                "  team <roster_id or name> [week]",
                "  roster <roster_id or name> [week]",
                "  transactions [--from <week_from>] [--to <week_to>] [--roster <roster_id or name>]",
                "  player <player_id or name> [week_to] [--log] [--from <week_from>] [--to <week_to>]",
                "  save [output_path]",
                "  sql <select_query>",
                "  help",
                "  exit | quit",
            ]
        )
    )


def _extract_flag_value(args: list[str], flag: str) -> tuple[str | None, str | None]:
    if flag not in args:
        return None, None
    idx = args.index(flag)
    if idx == len(args) - 1:
        return None, f"Missing value for {flag}"
    value = args[idx + 1]
    del args[idx : idx + 2]
    return value, None


def _extract_flag(args: list[str], flag: str) -> bool:
    if flag not in args:
        return False
    args.remove(flag)
    return True


def _run_app(league_id: str | None) -> int:
    data = SleeperLeagueData(league_id=league_id)
    data.load()
    _app_help()
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
        if raw == "help":
            _app_help()
            continue

        parts = raw.split()
        command = parts[0]
        args = parts[1:]

        try:
            if command == "snapshot":
                week = int(args[0]) if args else None
                _print_json(data.get_league_snapshot(week))
            elif command == "games":
                args = list(args)
                week_value, error = _extract_flag_value(args, "--week")
                if error:
                    print(
                        "Usage: games [--week <week>] [--roster <roster_id or name>] [--include-players]"
                    )
                    continue
                roster_key, error = _extract_flag_value(args, "--roster")
                if error:
                    print(
                        "Usage: games [--week <week>] [--roster <roster_id or name>] [--include-players]"
                    )
                    continue
                include_players = _extract_flag(args, "--include-players")
                if args:
                    print(
                        "Usage: games [--week <week>] [--roster <roster_id or name>] [--include-players]"
                    )
                    continue
                try:
                    week = int(week_value) if week_value is not None else None
                except ValueError:
                    print(
                        "Usage: games [--week <week>] [--roster <roster_id or name>] [--include-players]"
                    )
                    continue
                _print_json(
                    data.get_week_games(
                        week,
                        roster_key=roster_key,
                        include_players=include_players,
                    )
                )
            elif command == "team":
                if not args:
                    print("Usage: team <roster_id or name> [week]")
                    continue
                roster_key = args[0]
                week = int(args[1]) if len(args) > 1 else None
                _print_json(data.get_team_dossier(roster_key, week))
            elif command == "transactions":
                args = list(args)
                week_from_value, error = _extract_flag_value(args, "--from")
                if error:
                    print(
                        "Usage: transactions [--from <week_from>] [--to <week_to>] [--roster <roster_id or name>]"
                    )
                    continue
                week_to_value, error = _extract_flag_value(args, "--to")
                if error:
                    print(
                        "Usage: transactions [--from <week_from>] [--to <week_to>] [--roster <roster_id or name>]"
                    )
                    continue
                roster_key, error = _extract_flag_value(args, "--roster")
                if error:
                    print(
                        "Usage: transactions [--from <week_from>] [--to <week_to>] [--roster <roster_id or name>]"
                    )
                    continue
                if args:
                    print(
                        "Usage: transactions [--from <week_from>] [--to <week_to>] [--roster <roster_id or name>]"
                    )
                    continue
                context = data.conn.execute(
                    "SELECT effective_week FROM season_context LIMIT 1"
                ).fetchone()
                effective_week = int(context[0]) if context else 0
                try:
                    week_from = int(week_from_value) if week_from_value is not None else 1
                    week_to = (
                        int(week_to_value) if week_to_value is not None else effective_week
                    )
                except ValueError:
                    print(
                        "Usage: transactions [--from <week_from>] [--to <week_to>] [--roster <roster_id or name>]"
                    )
                    continue
                _print_json(
                    data.get_transactions(week_from, week_to, roster_key=roster_key)
                )
            elif command == "roster":
                if not args:
                    print("Usage: roster <roster_id or name> [week]")
                    continue
                roster_key = args[0]
                if len(args) > 1:
                    week = int(args[1])
                    _print_json(data.get_roster_snapshot(roster_key, week))
                else:
                    _print_json(data.get_roster_current(roster_key))
            elif command == "player":
                if not args:
                    print(
                        "Usage: player <player_id or name> [week_to] [--log] [--from <week_from>] [--to <week_to>]"
                    )
                    continue
                args = list(args)
                week_from_value, error = _extract_flag_value(args, "--from")
                if error:
                    print(
                        "Usage: player <player_id or name> [week_to] [--log] [--from <week_from>] [--to <week_to>]"
                    )
                    continue
                week_to_value, error = _extract_flag_value(args, "--to")
                if error:
                    print(
                        "Usage: player <player_id or name> [week_to] [--log] [--from <week_from>] [--to <week_to>]"
                    )
                    continue
                include_log = _extract_flag(args, "--log")
                if not args:
                    print(
                        "Usage: player <player_id or name> [week_to] [--log] [--from <week_from>] [--to <week_to>]"
                    )
                    continue
                positional_week_to = None
                name_tokens = args
                if len(args) > 1 and week_to_value is None:
                    try:
                        positional_week_to = int(args[-1])
                        name_tokens = args[:-1]
                    except ValueError:
                        positional_week_to = None
                        name_tokens = args
                player_key = " ".join(name_tokens).strip()
                if not player_key:
                    print(
                        "Usage: player <player_id or name> [week_to] [--log] [--from <week_from>] [--to <week_to>]"
                    )
                    continue
                try:
                    week_from = int(week_from_value) if week_from_value is not None else None
                    week_to = int(week_to_value) if week_to_value is not None else None
                    if week_to is None and positional_week_to is not None:
                        week_to = int(positional_week_to)
                except ValueError:
                    print(
                        "Usage: player <player_id or name> [week_to] [--log] [--from <week_from>] [--to <week_to>]"
                    )
                    continue
                if include_log:
                    _print_json(
                        data.get_player_weekly_log(
                            player_key,
                            week_from=week_from,
                            week_to=week_to,
                        )
                    )
                else:
                    _print_json(data.get_player_summary(player_key, week_to))
            elif command == "sql":
                if not args:
                    print("Usage: sql <select_query>")
                    continue
                query = raw[len("sql ") :]
                _print_json(data.run_sql(query))
            elif command == "save":
                output_path = args[0] if args else _default_output_path(data.league_id)
                if os.path.exists(output_path):
                    confirm = input(
                        f"{output_path} exists. Overwrite? [y/N] "
                    ).strip().lower()
                    if confirm not in {"y", "yes"}:
                        print("Save cancelled.")
                        continue
                saved_path = data.save_to_file(output_path)
                print(f"Saved SQLite snapshot to {saved_path}.")
            else:
                print("Unknown command. Type 'help' for options.")
        except Exception as exc:  # pragma: no cover - interactive convenience
            print(f"Error: {exc}")


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
