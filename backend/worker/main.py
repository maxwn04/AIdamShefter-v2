"""One-shot generation execution and stale-reconciliation commands."""

import argparse
import asyncio
from collections.abc import Callable, Sequence
from datetime import datetime
import json
import sys
from typing import Protocol, TextIO
from uuid import UUID

from backend.composition import (
    GenerationDependencies,
    GenerationRuntimeDependencies,
    build_worker_runtime,
)
from backend.resources.reporting.generations import GenerationStatus
from backend.services.generations import StaleGenerationPolicy
from backend.worker.dependencies import build_worker_generation_dependencies


RuntimeFactory = Callable[[], GenerationRuntimeDependencies]


class DependencyFactory(Protocol):
    def __call__(
        self,
        runtime: GenerationRuntimeDependencies,
        competition_id: UUID,
        *,
        correlation_id: UUID | None = None,
    ) -> GenerationDependencies: ...


def run(
    argv: Sequence[str] | None = None,
    *,
    runtime_factory: RuntimeFactory = build_worker_runtime,
    dependency_factory: DependencyFactory = build_worker_generation_dependencies,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    """Run exactly one explicit worker operation and release process resources."""

    arguments = _parser().parse_args(argv)
    try:
        runtime = runtime_factory()
    except Exception as exc:
        stderr.write(f"generation worker failed ({type(exc).__name__})\n")
        return 2
    try:
        runtime.assert_ready()
        dependencies = dependency_factory(runtime, arguments.competition_id)
        if arguments.command == "execute":
            result = asyncio.run(
                dependencies.service.execute(arguments.generation_id)
            )
            generation = result.generation
            _write_json(
                stdout,
                {
                    "generation_id": str(generation.id),
                    "status": generation.status.value,
                    "submitted_artifact_version_id": (
                        str(generation.submitted_artifact_version_id)
                        if generation.submitted_artifact_version_id is not None
                        else None
                    ),
                    "failure_category": generation.failure_category,
                    "failure_summary": generation.failure_summary,
                },
            )
            return 0 if generation.status is GenerationStatus.SUCCEEDED else 1

        result = dependencies.service.reconcile_stale(
            StaleGenerationPolicy(
                stale_before=arguments.stale_before,
                limit=arguments.limit,
            )
        )
        _write_json(
            stdout,
            {
                "stale_before": result.stale_before.isoformat(),
                "count": len(result.generations),
                "generation_ids": [
                    str(generation.id) for generation in result.generations
                ],
            },
        )
        return 0
    except Exception as exc:
        stderr.write(f"generation worker failed ({type(exc).__name__})\n")
        return 2
    finally:
        runtime.close()


def main() -> None:
    raise SystemExit(run())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aidam-worker")
    commands = parser.add_subparsers(dest="command", required=True)

    execute = commands.add_parser("execute")
    execute.add_argument("--competition-id", type=UUID, required=True)
    execute.add_argument("--generation-id", type=UUID, required=True)

    reconcile = commands.add_parser("reconcile-stale")
    reconcile.add_argument("--competition-id", type=UUID, required=True)
    reconcile.add_argument("--stale-before", type=_aware_datetime, required=True)
    reconcile.add_argument("--limit", type=int, default=100, choices=range(1, 201))
    return parser


def _aware_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("must include a UTC offset")
    return parsed


def _write_json(stream: TextIO, value: object) -> None:
    stream.write(json.dumps(value, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
