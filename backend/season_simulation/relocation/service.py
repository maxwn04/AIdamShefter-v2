"""Verify immutable continuation subsets and attest offline Linux bindings.

This module has no execution, credential-loading, database or provider command.
An attestation records runtime differences; it does not approve them for a run.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import stat
from typing import TYPE_CHECKING, Annotated, Any, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.resources._contracts import ContractModel
from backend.season_simulation.contracts import (
    Campaign,
    CampaignProgress,
    PreparedStep,
    RuntimeFreeze,
)
from backend.season_simulation.freeze import ROOT, file_hash, runtime_freeze
from backend.season_simulation.store import campaign_hash, load_campaign
from backend.services.generations.manifest import Sha256, canonical_json_sha256

if TYPE_CHECKING:
    from backend.season_simulation.controller import Reconciled


class FileEntry(BaseModel):
    """Source-relative provenance fields are retained by the manifest digest."""

    model_config = ConfigDict(extra="ignore")
    path: str
    bytes: Annotated[int, Field(strict=True, ge=0)]
    sha256: Sha256


class TransferManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    schema_version: Literal[1]
    subset: Literal[True]
    complete_original_export: Literal[False]
    campaign_id: UUID
    source_files: tuple[FileEntry, ...]
    generated_files: tuple[FileEntry, ...]


class PathBindings(ContractModel):
    import_root: Path
    campaign_directory: Path
    runtime_root: Path
    data_root: Path
    target_receipt: Path
    historical_data_root: str
    historical_target_file: str


class RelocationRecord(ContractModel):
    schema_version: Literal[1] = 1
    purpose: Literal["offline_inspection_only"] = "offline_inspection_only"
    execution_authorized: Literal[False] = False
    manifest_sha256: Sha256
    campaign_hash: Sha256
    bindings: PathBindings
    platform: dict[str, str]
    observed_runtime: RuntimeFreeze
    adapter_files: dict[str, Sha256]


def parse_json(data: bytes) -> Any:
    # Duplicate keys must not hide a different path, hash or campaign identity.
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    return json.loads(data, object_pairs_hook=unique)


def read_json(path: Path) -> Any:
    return parse_json(path.read_bytes())


def safe_file(root: Path, relative: str) -> Path:
    """Accept only canonical POSIX relative paths, never Windows path aliases."""
    parts = PurePosixPath(relative)
    if (
        not relative
        or parts.is_absolute()
        or parts.as_posix() != relative
        or any(part in {".", ".."} for part in parts.parts)
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


def authenticated_json(path: Path, expected: str) -> Any:
    # Read once so the digest and decoded document refer to identical bytes.
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("document SHA-256 differs from trusted digest")
    return parse_json(data)


@dataclass(frozen=True)
class VerifiedImport:
    bindings: PathBindings
    manifest_sha256: str
    campaign: Campaign
    progress: CampaignProgress
    assets: dict[str, str]
    next_step: int
    head: UUID
    generation_count: int
    indexed_heads: tuple[UUID, ...]
    next_status: str

    def asset_path(self, relative: str) -> Path:
        if relative not in self.assets:
            raise ValueError("asset is not declared in the verified import")
        path = safe_file(self.bindings.data_root, relative)
        if file_hash(path) != self.assets[relative]:
            raise ValueError("source asset changed after verification")
        return path

    def summary(self) -> dict[str, object]:
        return {
            "subset": True,
            "complete_original_export": False,
            "campaign_id": str(self.campaign.campaign_id),
            "campaign_hash": campaign_hash(self.campaign),
            "manifest_sha256": self.manifest_sha256,
            "source_assets": len(self.assets),
            "retained_generations": self.generation_count,
            "retained_head": str(self.head),
            "next_step": self.next_step,
            "retained_next_status": self.next_status,
            "next_week": (
                self.campaign.inputs.steps[self.next_step].week
                if self.next_step < len(self.campaign.inputs.steps)
                else None
            ),
            "index_receipts": len(self.indexed_heads),
            "retained_head_has_index_receipt": self.head in self.indexed_heads,
            "live_state_verified": False,
            "execution_authorized": False,
        }


def _retained_state(
    root: Path, campaign: Campaign, progress: CampaignProgress
) -> tuple[Reconciled, int, tuple[UUID, ...]]:
    # Lazy import: the CLI installs offline library settings before composition
    # imports. No imported historical module is put on sys.path or executed.
    from backend.resources.memory.revisions import CanonicalRevision
    from backend.resources.reporting.generations import Generation
    from backend.season_simulation.controller import CampaignBackend, reconcile

    rows = read_json(root / "evidence/tables/reporting.generations.json")
    generations = []
    for raw in rows:
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

    class EvidenceView:
        def generations(self) -> tuple[Generation, ...]:
            return tuple(generations)

        def revisions(self) -> tuple[CanonicalRevision, ...]:
            return tuple(revisions)

        def head(self) -> UUID:
            return UUID(current[0]["current_revision_id"])

    # Only the three read methods used by reconcile are exposed. Mutation,
    # execution, locks and live validation deliberately do not exist on this view.
    state = reconcile(campaign, progress, cast(CampaignBackend, EvidenceView()))
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
    return state, len(generations), tuple(indexed_heads)


def verify_import(root: Path, manifest_sha256: str) -> VerifiedImport:
    if root.is_symlink():
        raise ValueError("import root cannot be a symlink")
    root = root.resolve(strict=True)
    manifest = TransferManifest.model_validate(
        authenticated_json(safe_file(root, "transfer-manifest.json"), manifest_sha256)
    )
    entries = (*manifest.source_files, *manifest.generated_files)
    expected = {entry.path for entry in entries}
    if len(expected) != len(entries) or "transfer-manifest.json" in expected:
        raise ValueError("duplicate manifest path")
    if inventory(root) != expected | {"transfer-manifest.json"}:
        raise ValueError("evidence inventory differs from transfer manifest")
    for entry in entries:
        path = safe_file(root, entry.path)
        if path.stat().st_size != entry.bytes or file_hash(path) != entry.sha256:
            raise ValueError("evidence file size or SHA-256 changed")

    # Strict raw parsing catches duplicate keys before the existing typed loader.
    raw_campaign = read_json(root / "campaign/campaign.json")
    read_json(root / "campaign/progress.json")
    campaign, progress = load_campaign(root / "campaign")
    if campaign.campaign_id != manifest.campaign_id:
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
    if target != proof["target"]:
        raise ValueError("historical target receipt differs from operator proof")
    identity = target["identity"]
    unsigned = {key: value for key, value in target.items() if key != "identity"}
    if (
        hashlib.sha256(json.dumps(unsigned, sort_keys=True).encode()).hexdigest()
        != identity
        or identity != campaign.target_identity
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
    state, count, indexed = _retained_state(root, campaign, progress)
    bindings = PathBindings(
        import_root=root,
        campaign_directory=root / "campaign",
        runtime_root=runtime_root,
        data_root=root / "data",
        target_receipt=root / "control/hosted-target.json",
        historical_data_root=raw_campaign["inputs"]["data_root"],
        historical_target_file=raw_campaign["inputs"]["target_file"],
    )
    return VerifiedImport(
        bindings,
        manifest_sha256,
        campaign,
        progress,
        assets,
        state.next_step,
        state.head,
        count,
        indexed,
        (
            "complete"
            if state.next_step == len(campaign.inputs.steps)
            else str(state.latest.status)
            if state.latest is not None
            else "not_submitted"
        ),
    )


def measure(verified: VerifiedImport) -> RelocationRecord:
    if platform.system() != "Linux":
        raise ValueError("attestation requires native Linux or WSL2 Linux Python")
    return RelocationRecord(
        manifest_sha256=verified.manifest_sha256,
        campaign_hash=campaign_hash(verified.campaign),
        bindings=verified.bindings,
        platform={
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "implementation": platform.python_implementation(),
        },
        observed_runtime=runtime_freeze(verified.bindings.runtime_root),
        adapter_files=runtime_freeze(ROOT).files,
    )


def runtime_differences(
    verified: VerifiedImport, record: RelocationRecord
) -> list[str]:
    historical = verified.campaign.runtime
    return [
        field
        for field in RuntimeFreeze.model_fields
        if getattr(historical, field) != getattr(record.observed_runtime, field)
    ]


def attest(
    root: Path, manifest_sha256: str, output: Path
) -> tuple[RelocationRecord, str]:
    verified = verify_import(root, manifest_sha256)
    record = measure(verified)
    if output.resolve().is_relative_to(verified.bindings.import_root):
        raise ValueError("attestation must be outside immutable evidence")
    data = (record.model_dump_json(indent=2) + "\n").encode()
    # Exclusive creation: never overwrite another attestation or follow a link.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return record, hashlib.sha256(data).hexdigest()


def verify_record(
    path: Path, expected_sha256: str
) -> tuple[VerifiedImport, RelocationRecord]:
    record = RelocationRecord.model_validate(authenticated_json(path, expected_sha256))
    verified = verify_import(record.bindings.import_root, record.manifest_sha256)
    if measure(verified) != record:
        raise ValueError(
            "relocation paths, adapter or observed runtime changed; create a new reviewed record"
        )
    return verified, record


def main() -> None:
    # Force provider libraries to use their bundled metadata, without loading
    # any .env. These two process-only values are included in the measurement.
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "attest"):
        command = commands.add_parser(name)
        command.add_argument("--import-root", type=Path, required=True)
        command.add_argument("--manifest-sha256", required=True)
        if name == "attest":
            command.add_argument("--output", type=Path, required=True)
    command = commands.add_parser("verify")
    command.add_argument("--record", type=Path, required=True)
    command.add_argument("--record-sha256", required=True)
    args = parser.parse_args()
    try:
        if args.command == "verify":
            verified, record = verify_record(args.record, args.record_sha256)
            result = verified.summary()
            result["historical_runtime_differences"] = runtime_differences(
                verified, record
            )
        elif args.command == "attest":
            record, digest = attest(args.import_root, args.manifest_sha256, args.output)
            result = {
                "record_sha256": digest,
                "execution_authorized": False,
                "purpose": record.purpose,
            }
        else:
            result = verify_import(args.import_root, args.manifest_sha256).summary()
        print(json.dumps(result, indent=2))
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        IndexError,
        AttributeError,
    ) as exc:
        # ValidationError text can contain private input values. Do not echo it.
        parser.exit(
            2,
            f"Offline relocation validation failed ({type(exc).__name__}). No execution authorized.\n",
        )


if __name__ == "__main__":
    main()
