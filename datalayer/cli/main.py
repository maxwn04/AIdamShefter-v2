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
                "  games [week]",
                "  team <roster_id_or_name> [week]",
                "  roster <roster_id_or_name> [week]",
                "  transactions <week_from> <week_to>",
                "  player <player_id_or_name> [week_to]",
                "  save [output_path]",
                "  sql <select_query>",
                "  help",
                "  exit | quit",
            ]
        )
    )


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
                week = int(args[0]) if args else None
                _print_json(data.get_week_games(week))
            elif command == "team":
                if not args:
                    print("Usage: team <roster_id_or_name> [week]")
                    continue
                roster_key = args[0]
                week = int(args[1]) if len(args) > 1 else None
                _print_json(data.get_team_dossier(roster_key, week))
            elif command == "transactions":
                if len(args) < 2:
                    print("Usage: transactions <week_from> <week_to>")
                    continue
                week_from = int(args[0])
                week_to = int(args[1])
                _print_json(data.get_transactions(week_from, week_to))
            elif command == "roster":
                if not args:
                    print("Usage: roster <roster_id_or_name> [week]")
                    continue
                roster_key = args[0]
                if len(args) > 1:
                    week = int(args[1])
                    _print_json(data.get_roster_snapshot(roster_key, week))
                else:
                    _print_json(data.get_roster_current(roster_key))
            elif command == "player":
                if not args:
                    print("Usage: player <player_id_or_name> [week_to]")
                    continue
                player_key = args[0]
                week_to = int(args[1]) if len(args) > 1 else None
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
