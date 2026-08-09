"""Minimal maintenance CLI for the canonical-memory search projection."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import replace
import json
import sys
from uuid import UUID

from backend.config import DatabaseSettings
from backend.database.engine import build_runtime_engine
from backend.database.sessions import create_session_factory
from backend.resources.memory.errors import MemoryError
from backend.resources.memory.manager import MemoryManager
from backend.resources.memory.objects import RebuildResult, SearchIndexStatus
from backend.services.memory import MemorySearchIndexAdmin


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a valid UUID") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aidam-memory",
        description="Inspect or rebuild the canonical-memory search index.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="Show search-index status.")
    status.add_argument("competition_id", type=_uuid)

    rebuild = commands.add_parser("rebuild", help="Rebuild the search index.")
    rebuild.add_argument("competition_id", type=_uuid)
    return parser


def parse_args(args: Sequence[str]) -> argparse.Namespace:
    """Validate command-line values before constructing database resources."""

    return _build_parser().parse_args(args)


def format_result(result: SearchIndexStatus | RebuildResult) -> str:
    """Serialize the closed admin result contracts without adding CLI fields."""

    return json.dumps(result.model_dump(mode="json"), sort_keys=True)


def run(
    args: argparse.Namespace,
    admin: MemorySearchIndexAdmin,
) -> SearchIndexStatus | RebuildResult:
    """Execute one validated command against the narrow admin capability."""

    if args.command == "status":
        return admin.search_index_status(args.competition_id)
    if args.command == "rebuild":
        return admin.rebuild_search_index(args.competition_id)
    raise AssertionError(f"unhandled command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    """Build one process-local admin graph, execute, and release its engine."""

    args = parse_args(sys.argv[1:] if argv is None else argv)
    settings = DatabaseSettings.from_environment("worker")
    engine_settings = replace(
        settings.engine_settings("worker"),
        application_name="aidam-memory",
    )
    engine = build_runtime_engine(engine_settings)
    try:
        admin = MemoryManager(create_session_factory(engine))
        try:
            print(format_result(run(args, admin)))
        except MemoryError as error:
            print(
                json.dumps(
                    {
                        "error": {
                            "code": error.code,
                            "details": error.details,
                            "message": error.message,
                        }
                    },
                    default=str,
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 2
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
