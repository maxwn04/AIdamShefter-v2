"""Executable source-only bootstrap using normal backend refresh and preparation."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from sqlalchemy import create_engine, text

from backend.composition import (
    build_competition_catalog_dependencies,
    build_competition_season_dependencies,
    build_data_api_dependencies,
)
from backend.config import DatalayerSettings
from backend.database.sessions import create_session_factory
from backend.resources.context import (
    CompetitionScope, GlobalScope, ManagerContext, SystemProcessActor,
)
from backend.resources.core import CreateCompetition, CreateCompetitionSeason
from backend.season_simulation.docker import (
    DockerTarget, create_target, dump_database, restore_database, target_environment,
    verify_target,
)
from backend.services.datalayer.contracts import RefreshRequest, RefreshTrigger, SnapshotRequest
from backend.services.datalayer.snapshot_inputs import PrepareSnapshotRequest, SnapshotPreparationMode


def migrate_target(target: DockerTarget) -> None:
    verify_target(target)
    environment = {**os.environ, **target_environment(target), "AIDAM_MIGRATION_ROLE": "aidam_owner"}
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "backend/migrations/alembic.ini", "upgrade", "head"],
        env=environment, check=True,
        cwd=Path(__file__).resolve().parents[2],
    )


def export_assets(data_root: Path, destination: Path) -> list[dict[str, str | int]]:
    """Copy actual content-addressed files, rejecting links and verifying hashes."""
    records: list[dict[str, str | int]] = []
    for folder in ("payloads", "snapshots"):
        source_folder = data_root / folder
        if not source_folder.exists():
            continue
        for source in sorted(source_folder.rglob("*")):
            if source.is_symlink():
                raise ValueError("source assets must not contain symlinks")
            if not source.is_file():
                continue
            relative = source.relative_to(data_root)
            payload = source.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            if source.stem != digest:
                raise ValueError(f"source asset content hash mismatch: {relative}")
            output = destination / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_suffix(output.suffix + ".partial")
            temporary.write_bytes(payload)
            temporary.replace(output)
            records.append({"path": relative.as_posix(), "sha256": digest, "byte_length": len(payload)})
    return records


def prepare_target(
    target: DockerTarget,
    *,
    league_id: str,
    season_year: int,
    first_week: int,
    last_week: int,
    first_cutoff: datetime,
    model: str,
    request_template: str = "Write a weekly recap for week {week}.",
    settings: DatalayerSettings | None = None,
) -> Path:
    """Populate one fresh season, bootstrap roster identities, and seal inputs.

    Fetches free Sleeper source data only. No reporter/provider dependency is called.
    Failures retain their target for diagnosis; they never reset or reuse it.
    """
    if not 1 <= first_week <= last_week <= 18:
        raise ValueError("weeks must be ordered within 1..18")
    if first_cutoff.tzinfo is None or first_cutoff.utcoffset() is None:
        raise ValueError("first cutoff must have a timezone")
    if first_cutoff.year not in (season_year, season_year + 1):
        raise ValueError("editorial cutoff does not belong to the requested season")
    if not league_id.isdigit() or not model.strip():
        raise ValueError("a numeric Sleeper league ID and model are required")
    verify_target(target)
    root = Path(target.output_root)
    prepared_path = root / "prepared-inputs.json"
    if prepared_path.exists():
        raise FileExistsError("prepared target already exists")
    engine = create_engine(target_environment(target)["AIDAM_MIGRATION_DATABASE_URL"])
    try:
        with engine.connect() as connection:
            # This is deliberately global: preparation owns a brand new database.
            populated = connection.execute(text("SELECT EXISTS(SELECT 1 FROM core.competitions) OR EXISTS(SELECT 1 FROM reporting.generations) OR EXISTS(SELECT 1 FROM memory.memory_revisions)")).scalar_one()
            if populated:
                raise ValueError("source bootstrap requires an empty initialized database")
        sessions = create_session_factory(engine)
        actor = SystemProcessActor(process_name="season-simulation-bootstrap")
        global_context = ManagerContext(actor=actor, scope=GlobalScope(reason="new disposable source baseline"), correlation_id=uuid4())
        catalog = build_competition_catalog_dependencies(sessions, global_context)
        competition = catalog.competitions.create(CreateCompetition(display_name=f"Season simulation {season_year}"))
        context = ManagerContext(actor=actor, scope=CompetitionScope(competition_id=competition.id), correlation_id=uuid4())
        resolved = replace(settings or DatalayerSettings.from_environment(), data_root=root / "data")
        seasons = build_competition_season_dependencies(sessions, context, settings=resolved)
        season = seasons.seasons.create(CreateCompetitionSeason(season_year=season_year, sleeper_league_id=league_id))
        data = build_data_api_dependencies(sessions, context, settings=resolved)
        steps: list[dict[str, object]] = []
        required_snapshots: dict[str, str] = {}
        try:
            outcome = data.refresh.refresh(RefreshRequest(competition_season_id=season.id, through_week=last_week, trigger=RefreshTrigger.BACKFILL))
            mapping = seasons.roster_mappings.get_mapping(season.id)
            if mapping.status != "ready":
                raise ValueError(f"source roster bootstrap incomplete: {mapping.status}")
            for week in range(first_week, last_week + 1):
                cutoff = first_cutoff + timedelta(weeks=week - first_week)
                if cutoff > datetime.now(UTC):
                    raise ValueError("simulation preparation cannot claim a future reporting cutoff")
                prepared = data.preparation.get_or_create(PrepareSnapshotRequest(
                    snapshot=SnapshotRequest(competition_season_id=season.id, through_week=week, as_of_date=cutoff.date()),
                    mode=SnapshotPreparationMode.READINESS_ONLY,
                    requested_at=datetime.now(UTC),
                ))
                snapshot = prepared.snapshot
                if snapshot.input_revision is None:
                    raise ValueError("prepared snapshot lacks frozen input revision")
                required_snapshots[snapshot.artifact.storage_key] = snapshot.artifact.sha256
                steps.append({
                    "week": week,
                    "snapshot_id": str(snapshot.id),
                    "artifact_sha256": snapshot.artifact.sha256,
                    "input_revision": snapshot.input_revision,
                    "editorial_cutoff_at": cutoff.isoformat(),
                })
        finally:
            data.close()
        with engine.connect() as connection:
            if connection.execute(text("SELECT EXISTS(SELECT 1 FROM reporting.generations) OR EXISTS(SELECT 1 FROM memory.memory_revisions)")).scalar_one():
                raise ValueError("source-only baseline unexpectedly contains reporter state")
        seed = root / "source-only"
        seed.mkdir(exist_ok=True)
        assets = export_assets(resolved.data_root, seed / "data")
        exported = {str(asset["path"]): asset["sha256"] for asset in assets}
        if any(exported.get(path) != digest for path, digest in required_snapshots.items()):
            raise ValueError("source-only export is missing a prepared snapshot asset")
        dump = dump_database(target, seed / "database.dump")
        manifest = {
            "schema_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "source_refresh_id": str(outcome.refresh_run_id),
            "source_refresh_status": str(outcome.status),
            "database_sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
            "assets": assets,
            "limitations": [
                "Retrospective cutoff reconstruction; source observation timestamps are real fetch times.",
                "Historical injuries/news and changing current-state attributes are not faithful historical observations.",
                "Only this explicitly registered season is included; no inferred prior-season franchise continuity.",
            ],
        }
        (seed / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        prepared_json = json.dumps({
            "competition_id": str(competition.id),
            "competition_season_id": str(season.id),
            "season_year": season_year,
            "data_root": str(resolved.data_root.resolve()),
            "target_file": str((root / "target.json").resolve()),
            "steps": steps,
            "model": model,
            "request_template": request_template,
        }, indent=2) + "\n"
        (seed / "prepared-inputs.json").write_text(prepared_json, encoding="utf-8")
        prepared_path.write_text(prepared_json, encoding="utf-8")
        return prepared_path
    finally:
        engine.dispose()


def restore_source_baseline(*, source: Path, name: str, output_root: Path, port: int) -> Path:
    """Recover a preserved empty-memory seed into another new disposable target."""
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    dump = source / "database.dump"
    if hashlib.sha256(dump.read_bytes()).hexdigest() != manifest["database_sha256"]:
        raise ValueError("source-only database hash mismatch")
    prepared = json.loads((source / "prepared-inputs.json").read_text(encoding="utf-8"))
    # Verify every declared asset before allocating the new target.
    for asset in manifest["assets"]:
        path = (source / "data" / asset["path"]).resolve()
        if not path.is_relative_to((source / "data").resolve()):
            raise ValueError("source asset escapes export root")
        content = path.read_bytes()
        if len(content) != asset["byte_length"] or hashlib.sha256(content).hexdigest() != asset["sha256"]:
            raise ValueError("source-only asset hash mismatch")
    target = create_target(name=name, output_root=output_root, port=port)
    restore_database(target, dump)
    data_root = Path(target.output_root) / "data"
    restored = export_assets(source / "data", data_root)
    if restored != manifest["assets"]:
        raise ValueError("source-only asset manifest differs from restored assets")
    prepared["data_root"] = str(data_root.resolve())
    prepared["target_file"] = str(Path(target.output_root) / "target.json")
    destination = Path(target.output_root) / "prepared-inputs.json"
    destination.write_text(json.dumps(prepared, indent=2) + "\n", encoding="utf-8")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Create a NEW isolated target, migrate, fetch free sources, and prepare snapshots")
    prepare.add_argument("--name", required=True)
    prepare.add_argument("--output-root", required=True, type=Path)
    prepare.add_argument("--port", type=int, default=55441)
    prepare.add_argument("--league-id", required=True)
    prepare.add_argument("--season", required=True, type=int)
    prepare.add_argument("--first-week", type=int, default=1)
    prepare.add_argument("--last-week", required=True, type=int)
    prepare.add_argument("--first-cutoff", required=True, type=datetime.fromisoformat)
    prepare.add_argument("--model", required=True)
    prepare.add_argument("--request-template", default="Write a weekly recap for week {week}.")
    restore = commands.add_parser("restore", help="Restore a source-only baseline to another NEW target without fetching")
    restore.add_argument("--source", required=True, type=Path)
    restore.add_argument("--name", required=True)
    restore.add_argument("--output-root", required=True, type=Path)
    restore.add_argument("--port", type=int, default=55441)
    args = parser.parse_args()
    if args.command == "restore":
        print(restore_source_baseline(source=args.source, name=args.name, output_root=args.output_root, port=args.port))
        return
    target = create_target(name=args.name, output_root=args.output_root, port=args.port)
    migrate_target(target)
    result = prepare_target(target, league_id=args.league_id, season_year=args.season, first_week=args.first_week, last_week=args.last_week, first_cutoff=args.first_cutoff, model=args.model, request_template=args.request_template)
    print(result)


if __name__ == "__main__":
    main()
