"""Complete offline inspection and recovery bundles, published only when complete."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from uuid import UUID, uuid4

from sqlalchemy import Engine, select

from backend.database.registry import metadata
from backend.database.sessions import create_session_factory
from backend.resources.context import CompetitionScope, ManagerContext, SystemProcessActor
from backend.resources.reporting.ai_calls import AICallManager
from backend.season_simulation.bootstrap import export_assets
from backend.season_simulation.contracts import Campaign, CampaignProgress
from backend.season_simulation.docker import DockerTarget, dump_database
from backend.season_simulation.freeze import file_hash
from backend.season_simulation.store import write_json
from backend.services.model_usage.pricing import LiteLLMModelRegistry
from backend.services.model_usage.usage import GenerationUsageService


def export_campaign(directory: Path, campaign: Campaign, progress: CampaignProgress,
                    engine: Engine, target: DockerTarget, *, dump=dump_database) -> Path:
    """Retain full rows, traces and assets; failed staging never replaces a good export."""
    export_root = directory / "exports"
    staging = export_root / f".partial-{uuid4().hex}"
    staging.mkdir(parents=True)
    # A failed staging directory is retained for diagnosis; another export starts
    # independently. No generation is ever submitted by this operation.
    tables: dict[str, list[dict]] = {}
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        for name, table in sorted(metadata.tables.items()):
            statement = select(table).order_by(*table.primary_key.columns)
            tables[name] = [dict(row) for row in connection.execute(statement).mappings()]
    for name, rows in tables.items():
        write_json(staging / "tables" / f"{name}.json", rows)
    write_json(staging / "campaign.json", campaign.model_dump(mode="json"))
    write_json(staging / "progress.json", progress.model_dump(mode="json"))
    assets = export_assets(campaign.inputs.data_root, staging / "data")
    # Every external artifact referenced by the database must really be in the
    # bundle. Include source payloads too: they are needed for source-only replay.
    exported = {str(record["path"]): record for record in assets}
    for row in tables["sleeper.data_snapshots"]:
        key = row.get("sqlite_artifact_storage_key")
        if key is not None:
            record = exported.get(str(key))
            if record is None or record["sha256"] != row["sqlite_artifact_sha256"]:
                raise ValueError("export missing a referenced frozen snapshot asset")
    for row in tables["sleeper.api_payloads"]:
        key = row.get("object_storage_key")
        if key is not None:
            record = exported.get(str(key))
            if record is None or record["sha256"] != row["sha256_hash"] or record["byte_length"] != row["byte_length"]:
                raise ValueError("export missing or corrupt referenced source payload")
    frozen = directory / "runtime"
    if file_hash(frozen / "model-prices.json") != campaign.runtime.pricing_sha256:
        raise ValueError("archived pricing asset changed")
    (staging / "runtime").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(frozen / "model-prices.json", staging / "runtime/model-prices.json")
    for relative, digest in campaign.runtime.files.items():
        source = frozen / relative
        if file_hash(source) != digest:
            raise ValueError("archived runtime asset changed")
        destination = staging / "runtime" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    versions = {str(row["id"]): row for row in tables["reporting.artifact_versions"]}
    artifacts = {str(row["id"]): row for row in tables["reporting.artifacts"]}
    index = []
    for generation in tables["reporting.generations"]:
        gid = str(generation["id"])
        own_versions = [version for version in versions.values() if str(version["generation_id"]) == gid]
        for version in own_versions:
            # User/model-controlled artifact paths never become filesystem paths.
            artifact = artifacts[str(version["artifact_id"])]
            version_id = str(version["id"])
            path = staging / "generations" / gid / f"{version_id}.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(version["content"], encoding="utf-8", newline="\n")
            write_json(path.with_suffix(".json"), {"original_path": artifact["path"], **version})
        submitted = generation["submitted_artifact_version_id"]
        index.append({
            "generation_id": gid, "week": generation["week_end"], "status": generation["status"],
            "input_memory_revision_id": generation["input_memory_revision_id"],
            "output_memory_revision_id": next((row["id"] for row in tables["memory.memory_revisions"]
                                               if row["producing_generation_id"] == generation["id"]),
                                              generation["input_memory_revision_id"] if generation["status"] == "succeeded" else None),
            "article": f"generations/{gid}/{submitted}.txt" if submitted else None,
        })
    write_json(staging / "season-index.json", sorted(index, key=lambda row: (row["week"], row["generation_id"])))
    context = ManagerContext(actor=SystemProcessActor(process_name="season-export"),
                             scope=CompetitionScope(competition_id=campaign.inputs.competition_id), correlation_id=uuid4())
    # Load the archived campaign price table, never a live catalog. Missing usage
    # and unpriced calls retain their ordinary explicit incomplete status.
    prices = json.loads((frozen / "model-prices.json").read_text(encoding="utf-8"))
    usage = GenerationUsageService(AICallManager(create_session_factory(engine), context),
                                   LiteLLMModelRegistry(remote_loader=lambda: prices))
    write_json(staging / "usage.json", [usage.get(UUID(item["generation_id"])).model_dump(mode="json") for item in index])
    dump(target, staging / "database.dump")
    (staging / "README.md").write_text(
        "# Retained season campaign\n\n"
        "season-index.json links articles and exact input/output memory heads.\n"
        "tables/ retains every database row: complete model messages/responses, tool\n"
        "results/metadata, briefs and all artifact versions, usage and memory versions.\n"
        "data/ contains actual frozen snapshots and source payloads. runtime/ contains\n"
        "the frozen backend source; campaign.json records dependency versions/config.\n"
        "Restore database.dump ONLY into a new isolated target with matching roles and\n"
        "copy data/ to its configured AIDAM_DATALAYER_ROOT. See the operator runbook.\n"
        "The original campaign receipt is required to resume its retained container;\n"
        "an offline restore is for inspection or a new campaign, never a silent rebind.\n",
        encoding="utf-8",
    )
    records = {path.relative_to(staging).as_posix(): file_hash(path)
               for path in sorted(staging.rglob("*")) if path.is_file()}
    # Hashes make partial/corrupted copies visible independently of the database.
    write_json(staging / "export-manifest.json", {"schema_version": 1, "files": records, "assets": assets})
    output = export_root / f"export-{uuid4().hex}"
    staging.rename(output)
    write_json(export_root / "latest.json", {"directory": output.name, "manifest_sha256": file_hash(output / "export-manifest.json")})
    return output


def verify_export(directory: Path) -> None:
    manifest = json.loads((directory / "export-manifest.json").read_text(encoding="utf-8"))
    for relative, expected in manifest["files"].items():
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory.resolve()) or file_hash(path) != expected:
            raise ValueError("export file missing, outside bundle, or corrupt")
