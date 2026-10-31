"""Check a retained campaign subset and report runtime differences; never resume it.

Run from the repository root with PYTHON_DOTENV_DISABLED=1 and
LITELLM_LOCAL_MODEL_COST_MAP=True using the project Python environment.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
from typing import Any, cast
from uuid import UUID

from backend.resources.memory.revisions import CanonicalRevision
from backend.resources.reporting.generations import Generation
from backend.season_simulation.contracts import Campaign, CampaignProgress, PreparedStep
from backend.season_simulation.controller import CampaignBackend, reconcile
from backend.season_simulation.freeze import file_hash, runtime_freeze
from backend.season_simulation.store import load_campaign
from backend.services.generations.manifest import canonical_json_sha256


def parse_json(data: bytes) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    return json.loads(data, object_pairs_hook=unique)


def read_json(path: Path) -> Any:
    return parse_json(path.read_bytes())


def safe_file(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative)
    if (
        not relative
        or parts.is_absolute()
        or parts.as_posix() != relative
        or ".." in parts.parts
        or "\\" in relative
        or ":" in relative
    ):
        raise ValueError("unsafe relative evidence path")
    path = root
    for part in parts.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("symlink in evidence path")
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("missing or escaped evidence file")
    return path


def inventory(root: Path) -> set[str]:
    result = set()
    for path in root.rglob("*"):
        mode = path.lstat().st_mode
        if stat.S_ISREG(mode):
            result.add(path.relative_to(root).as_posix())
        elif not stat.S_ISDIR(mode):
            raise ValueError("special file or symlink in evidence tree")
    return result


@dataclass
class RetainedHistory:
    """Only the three read operations used by the existing reconciler."""

    rows: tuple[Generation, ...]
    history: tuple[CanonicalRevision, ...]
    current: UUID

    def generations(self) -> tuple[Generation, ...]:
        return self.rows

    def revisions(self) -> tuple[CanonicalRevision, ...]:
        return self.history

    def head(self) -> UUID:
        return self.current


def check_history(
    root: Path, campaign: Campaign, progress: CampaignProgress
) -> dict[str, Any]:
    generations = []
    for raw in read_json(root / "evidence/tables/reporting.generations.json"):
        row = dict(raw)
        row["settings"] = row.pop("settings_jsonb")
        row["input_manifest"] = row.pop("input_manifest_jsonb")
        generation = Generation.model_validate(row)
        if generation.input_manifest is not None:
            if (
                canonical_json_sha256(generation.input_manifest)
                != generation.manifest_hash
            ):
                raise ValueError("retained generation manifest hash changed")
        elif generation.manifest_hash is not None or generation.status == "succeeded":
            raise ValueError("retained generation manifest is missing")
        generations.append(generation)
    revisions = []
    for raw in read_json(root / "evidence/tables/memory.memory_revisions.json"):
        row = dict(raw)
        row["revision_id"] = row.pop("id")
        revisions.append(CanonicalRevision.model_validate(row))
    revisions.sort(key=lambda row: row.sequence_number)
    current = read_json(root / "evidence/tables/memory.current_revisions.json")
    if (
        len(current) != 1
        or current[0]["competition_id"] != str(campaign.inputs.competition_id)
        or any(
            row.competition_id != campaign.inputs.competition_id
            for row in (*generations, *revisions)
        )
        or len({row.id for row in generations}) != len(generations)
        or len({row.revision_id for row in revisions}) != len(revisions)
        or [row.sequence_number for row in revisions] != list(range(len(revisions)))
    ):
        raise ValueError("ambiguous retained identities or revision sequence")
    history = RetainedHistory(
        tuple(generations), tuple(revisions), UUID(current[0]["current_revision_id"])
    )
    # Reuse the controller's request/attempt/snapshot/lineage rules. This view
    # deliberately has no submit, execute, database or mutation operation.
    state = reconcile(campaign, progress, cast(CampaignBackend, history))
    indexed_heads = []
    for path in sorted((root / "campaign/indexing").glob("*/receipt.json")):
        receipt = read_json(path)
        if receipt.get("complete"):
            if (
                receipt.get("canonical_unchanged") is not True
                or receipt["before"] != receipt["after"]
            ):
                raise ValueError("index receipt changed canonical memory")
            before = CanonicalRevision.model_validate(receipt["before"])
            if before not in revisions:
                raise ValueError("index receipt has an unrelated canonical revision")
            indexed_heads.append(before.revision_id)
    complete = state.next_step == len(campaign.inputs.steps)
    return {
        "retained_generations": len(generations),
        "retained_head": str(state.head),
        "next_week": None if complete else campaign.inputs.steps[state.next_step].week,
        "retained_next_status": "complete"
        if complete
        else str(state.latest.status)
        if state.latest
        else "not_submitted",
        "complete_index_receipts": len(indexed_heads),
        "retained_head_has_index_receipt": state.head in indexed_heads,
    }


def verify_import(root: Path, manifest_sha256: str) -> dict[str, Any]:
    if root.is_symlink():
        raise ValueError("import root cannot be a symlink")
    root = root.resolve(strict=True)
    raw = safe_file(root, "transfer-manifest.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest_sha256:
        raise ValueError("transfer manifest differs from trusted SHA-256")
    manifest = parse_json(raw)
    if (
        manifest["schema_version"] != 1
        or manifest["subset"] is not True
        or manifest["complete_original_export"] is not False
    ):
        raise ValueError("expected a version-1 incomplete continuation subset")
    entries = manifest["source_files"] + manifest["generated_files"]
    expected = {entry["path"] for entry in entries}
    if len(expected) != len(entries) or "transfer-manifest.json" in expected:
        raise ValueError("duplicate manifest path")
    if inventory(root) != expected | {"transfer-manifest.json"}:
        raise ValueError("evidence inventory differs from transfer manifest")
    for entry in entries:
        path = safe_file(root, entry["path"])
        if path.stat().st_size != entry["bytes"] or file_hash(path) != entry["sha256"]:
            raise ValueError("evidence file size or SHA-256 changed")

    raw_campaign = read_json(root / "campaign/campaign.json")
    read_json(
        root / "campaign/progress.json"
    )  # Reject duplicate keys before the typed loader.
    campaign, progress = load_campaign(root / "campaign")
    if str(campaign.campaign_id) != manifest["campaign_id"]:
        raise ValueError("transfer campaign identity differs")
    runtime_root = root / "campaign/runtime"
    if inventory(runtime_root) != set(campaign.runtime.files) | {"model-prices.json"}:
        raise ValueError("unsealed historical runtime files")
    for relative, digest in campaign.runtime.files.items():
        if file_hash(safe_file(runtime_root, relative)) != digest:
            raise ValueError("historical runtime source hash changed")
    if file_hash(runtime_root / "model-prices.json") != campaign.runtime.pricing_sha256:
        raise ValueError("historical pricing hash changed")
    proof = read_json(root / "campaign/operator-proof.json")
    if (
        file_hash(root / "control/canonical_ops.py") != proof["sha256"]
        or file_hash(root / "campaign/preview-step.json") != proof["preview_sha256"]
    ):
        raise ValueError("historical operator or preview changed")
    target = read_json(root / "control/hosted-target.json")
    unsigned = {key: value for key, value in target.items() if key != "identity"}
    if (
        target != proof["target"]
        or hashlib.sha256(json.dumps(unsigned, sort_keys=True).encode()).hexdigest()
        != target["identity"]
        or target["identity"] != campaign.target_identity
        or target["competition_id"] != str(campaign.inputs.competition_id)
        or target["data_root"] != raw_campaign["inputs"]["data_root"]
    ):
        raise ValueError("historical target identity differs from campaign")
    export = read_json(root / "evidence/export-manifest.json")
    if export["schema_version"] != 1:
        raise ValueError("unsupported export asset manifest version")
    assets = {}
    for asset in export["assets"]:
        relative = asset["path"]
        if relative in assets:
            raise ValueError("duplicate source asset")
        path = safe_file(root / "data", relative)
        if (
            path.stat().st_size != asset["byte_length"]
            or file_hash(path) != asset["sha256"]
        ):
            raise ValueError("source asset differs from original export")
        assets[relative] = asset["sha256"]
    preview = PreparedStep.model_validate(
        read_json(root / "campaign/preview-step.json")
    )
    if any(
        step.artifact_sha256 not in assets.values()
        for step in (*campaign.inputs.steps, preview)
    ):
        raise ValueError("prepared snapshot is missing from retained assets")

    observed = runtime_freeze(runtime_root)
    changes: dict[str, Any] = {}
    for name in ("python", "pricing_sha256"):
        before, after = getattr(campaign.runtime, name), getattr(observed, name)
        if before != after:
            changes[name] = {"frozen": before, "current": after}
    if observed.packages != campaign.runtime.packages:
        before, after = campaign.runtime.packages, observed.packages
        changes["packages"] = {
            name: {"frozen": before.get(name), "current": after.get(name)}
            for name in sorted(before.keys() | after.keys())
            if before.get(name) != after.get(name)
        }
    if observed.configuration != campaign.runtime.configuration:
        changes["configuration"] = sorted(
            name
            for name in observed.configuration.keys()
            | campaign.runtime.configuration.keys()
            if observed.configuration.get(name)
            != campaign.runtime.configuration.get(name)
        )
    return {
        "scope": "retained_files_only",
        "complete_original_export": False,
        "verified_files": len(entries),
        "source_assets": len(assets),
        **check_history(root, campaign, progress),
        "runtime_differences": changes,
        "live_state_verified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--import-root", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    try:
        print(
            json.dumps(verify_import(args.import_root, args.manifest_sha256), indent=2)
        )
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        IndexError,
        AttributeError,
    ) as exc:
        # Validation errors may contain private input values; don't echo them.
        parser.exit(
            2, f"Import verification failed ({type(exc).__name__}). No files changed.\n"
        )


if __name__ == "__main__":
    main()
