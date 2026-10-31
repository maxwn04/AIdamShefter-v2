"""Synthetic evidence only: no private exports, database or provider calls."""

import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
from uuid import uuid4

import pytest

from backend.season_simulation.contracts import (
    Campaign,
    CampaignProgress,
    PreparedInputs,
    PreparedStep,
    RuntimeFreeze,
    StepProgress,
)
from backend.season_simulation.controller import step_request
from backend.season_simulation.relocation import service as relocation
from backend.season_simulation.store import campaign_hash, write_json
from backend.services.generations.manifest import canonical_json_sha256
from backend.tests.season_simulation.test_controller import FakeBackend


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: Path):
    return json.loads(path.read_text())


def seal(root: Path) -> str:
    """Simulate an independently verified transfer of a synthetic export."""
    entries = [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": digest(path.read_bytes()),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "transfer-manifest.json"
    ]
    campaign = read(root / "campaign/campaign.json")
    write_json(
        root / "transfer-manifest.json",
        {
            "schema_version": 1,
            "subset": True,
            "complete_original_export": False,
            "campaign_id": campaign["campaign_id"],
            "source_files": entries,
            "generated_files": [],
        },
    )
    return digest((root / "transfer-manifest.json").read_bytes())


@pytest.fixture
def imported(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline relocation attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    root = tmp_path / "private-import"
    runtime = root / "campaign/runtime"
    (runtime / "backend").mkdir(parents=True)
    # Syntax is deliberately unexecutable: verification must never import it.
    source = b"raise AssertionError('do not execute archived code')\r\n"
    (runtime / "backend/frozen.py").write_bytes(source)
    (runtime / "model-prices.json").write_bytes(b"{}")
    payload = b"synthetic snapshot bytes; never open as a database"
    data = root / "data/snapshots/one.sqlite"
    data.parent.mkdir(parents=True)
    data.write_bytes(payload)
    competition, season = uuid4(), uuid4()
    target = {
        "host": "synthetic.invalid",
        "port": 5432,
        "database": "test",
        "username": "test_worker",
        "competition_id": str(competition),
        "data_root": "C:\\synthetic\\data",
    }
    target["identity"] = digest(json.dumps(target, sort_keys=True).encode())
    steps = tuple(
        PreparedStep(
            week=week,
            snapshot_id=uuid4(),
            artifact_sha256=digest(payload),
            input_revision="b" * 64,
            editorial_cutoff_at=datetime(2025, 9, 10, tzinfo=UTC)
            + timedelta(weeks=week),
            request_text=f"Synthetic request {week}",
        )
        for week in (1, 2)
    )
    campaign = Campaign(
        campaign_id=uuid4(),
        root_revision_id=uuid4(),
        root_state_hash="a" * 64,
        target_identity=target["identity"],
        inputs=PreparedInputs(
            competition_id=competition,
            competition_season_id=season,
            season_year=2025,
            data_root=Path(target["data_root"]),
            target_file=Path("C:\\synthetic\\target.json"),
            steps=steps,
            model="scripted",
        ),
        runtime=RuntimeFreeze(
            files={"backend/frozen.py": digest(source)},
            packages={"synthetic": "1"},
            python="3.11.16",
            configuration={},
            pricing_sha256=digest(b"{}"),
        ),
    )
    progress = CampaignProgress(
        campaign_hash=campaign_hash(campaign),
        steps=tuple(StepProgress() for _ in steps),
    )
    write_json(root / "campaign/campaign.json", campaign.model_dump(mode="json"))
    write_json(root / "campaign/progress.json", progress.model_dump(mode="json"))
    write_json(root / "control/hosted-target.json", target)
    (root / "control/canonical_ops.py").write_bytes(b"do not execute\r\n")
    write_json(root / "campaign/preview-step.json", steps[0].model_dump(mode="json"))
    write_json(
        root / "campaign/operator-proof.json",
        {
            "sha256": digest((root / "control/canonical_ops.py").read_bytes()),
            "preview_sha256": digest(
                (root / "campaign/preview-step.json").read_bytes()
            ),
            "target": target,
        },
    )
    write_json(
        root / "evidence/export-manifest.json",
        {
            "schema_version": 1,
            "files": {},
            "assets": [
                {
                    "path": "snapshots/one.sqlite",
                    "byte_length": len(payload),
                    "sha256": digest(payload),
                }
            ],
        },
    )
    backend = FakeBackend(campaign)
    request = step_request(campaign, 0, 1, campaign.root_revision_id)
    backend.submit(request)
    asyncio.run(backend.execute(request.generation_id))
    row = backend.rows[request.generation_id].model_dump(mode="json")
    row["settings_jsonb"] = row.pop("settings")
    row["input_manifest_jsonb"] = {"synthetic": "frozen manifest"}
    row.pop("input_manifest")
    row["manifest_hash"] = canonical_json_sha256(row["input_manifest_jsonb"])
    write_json(root / "evidence/tables/reporting.generations.json", [row])
    revisions = []
    for revision in backend.history:
        raw = revision.model_dump(mode="json")
        raw["id"] = raw.pop("revision_id")
        revisions.append(raw)
    write_json(root / "evidence/tables/memory.memory_revisions.json", revisions)
    write_json(
        root / "evidence/tables/memory.current_revisions.json",
        [
            {
                "competition_id": str(competition),
                "current_revision_id": str(backend.head()),
            }
        ],
    )
    boundary = backend.history[-1].model_dump(mode="json")
    write_json(
        root / "campaign/indexing/one/receipt.json",
        {
            "before": boundary,
            "after": boundary,
            "canonical_unchanged": True,
            "complete": True,
        },
    )
    return root, seal(root), campaign


def test_offline_binding_preserves_windows_identity_and_requests(imported):
    root, sha, campaign = imported
    before = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    verified = relocation.verify_import(root, sha)
    assert verified.campaign == campaign
    assert verified.next_step == 1
    assert verified.summary()["next_week"] == 2
    assert verified.summary()["retained_head_has_index_receipt"] is True
    assert verified.bindings.historical_data_root == "C:\\synthetic\\data"
    assert (
        verified.asset_path("snapshots/one.sqlite")
        == root / "data/snapshots/one.sqlite"
    )
    request = step_request(verified.campaign, 1, 1, verified.head)
    assert request.generation_id == campaign.generation_id(1, 1)
    assert request.request_text == "Synthetic request 2"
    assert (
        request.settings.prepared_execution.expected_memory_revision_id == verified.head
    )
    assert {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize(
    "relative", ["../escape", "/tmp/escape", "C:\\data", "a//b", "./a", "a/../b", ""]
)
def test_paths_must_be_canonical_and_contained(tmp_path, relative):
    with pytest.raises(ValueError):
        relocation.safe_file(tmp_path, relative)


@pytest.mark.parametrize(
    "mutation", ["changed", "missing", "extra", "symlink", "duplicate", "manifest"]
)
def test_transfer_integrity_fails_closed(imported, mutation):
    root, sha, _ = imported
    payload = root / "data/snapshots/one.sqlite"
    if mutation == "changed":
        payload.write_bytes(b"tampered")
    elif mutation == "missing":
        payload.unlink()
    elif mutation == "extra":
        (root / "unlisted.py").write_text("unsealed")
    elif mutation == "symlink":
        payload.unlink()
        payload.symlink_to(root / "campaign/campaign.json")
    elif mutation == "duplicate":
        manifest = read(root / "transfer-manifest.json")
        manifest["source_files"].append(manifest["source_files"][0])
        write_json(root / "transfer-manifest.json", manifest)
        sha = digest((root / "transfer-manifest.json").read_bytes())
    else:
        (root / "transfer-manifest.json").write_text("{}")
    with pytest.raises(ValueError):
        relocation.verify_import(root, sha)


@pytest.mark.parametrize(
    "mutation",
    [
        "operator",
        "runtime_crlf",
        "pricing",
        "target_login",
        "progress",
        "request",
        "settings",
        "snapshot",
        "head",
        "lineage",
        "manifest_hash",
        "duplicate_generation",
        "duplicate_revision",
        "revision_sequence",
        "competition",
        "index",
        "preview",
        "asset",
    ],
)
def test_historical_guards_survive_transfer_resealing(imported, mutation):
    root, _, _ = imported
    # A correctly packaged but internally inconsistent export must still fail.
    files = {
        "target_login": "control/hosted-target.json",
        "progress": "campaign/progress.json",
        "request": "evidence/tables/reporting.generations.json",
        "settings": "evidence/tables/reporting.generations.json",
        "snapshot": "evidence/tables/reporting.generations.json",
        "manifest_hash": "evidence/tables/reporting.generations.json",
        "duplicate_generation": "evidence/tables/reporting.generations.json",
        "head": "evidence/tables/memory.current_revisions.json",
        "lineage": "evidence/tables/memory.memory_revisions.json",
        "duplicate_revision": "evidence/tables/memory.memory_revisions.json",
        "revision_sequence": "evidence/tables/memory.memory_revisions.json",
        "competition": "evidence/tables/memory.memory_revisions.json",
        "index": "campaign/indexing/one/receipt.json",
        "preview": "campaign/preview-step.json",
    }
    if mutation in files:
        path = root / files[mutation]
        value = read(path)
        if mutation == "target_login":
            value["username"] = "another_login"
        elif mutation == "progress":
            value["campaign_hash"] = "0" * 64
        elif mutation == "request":
            value[0]["request_text"] = "changed"
        elif mutation == "settings":
            value[0]["settings_jsonb"]["runner"]["max_turns"] = 1
        elif mutation == "snapshot":
            value[0]["data_snapshot_id"] = str(uuid4())
        elif mutation == "manifest_hash":
            value[0]["manifest_hash"] = "0" * 64
        elif mutation in {"duplicate_generation", "duplicate_revision"}:
            value.append(value[0])
        elif mutation == "head":
            value[0]["current_revision_id"] = str(uuid4())
        elif mutation == "lineage":
            value[1]["previous_revision_id"] = str(uuid4())
        elif mutation == "revision_sequence":
            value[1]["sequence_number"] = 4
        elif mutation == "competition":
            value[0]["competition_id"] = str(uuid4())
        elif mutation == "index":
            value["after"]["state_content_hash"] = "0" * 64
        elif mutation == "preview":
            value["input_revision"] = "0" * 64
        write_json(path, value)
    else:
        path = (
            root
            / {
                "operator": "control/canonical_ops.py",
                "runtime_crlf": "campaign/runtime/backend/frozen.py",
                "pricing": "campaign/runtime/model-prices.json",
                "asset": "data/snapshots/one.sqlite",
            }[mutation]
        )
        path.write_bytes(
            path.read_bytes().replace(b"\r\n", b"\n")
            if mutation == "runtime_crlf"
            else b"changed"
        )
    with pytest.raises(ValueError):
        relocation.verify_import(root, seal(root))


def test_attestation_detects_drift_without_authorizing_execution(
    imported, tmp_path, monkeypatch
):
    root, sha, _ = imported
    output = tmp_path / "relocation.json"
    record, digest_value = relocation.attest(root, sha, output)
    verified, read_record = relocation.verify_record(output, digest_value)
    assert read_record == record
    assert record.execution_authorized is False
    assert "packages" in relocation.runtime_differences(verified, record)
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        relocation.attest(root, sha, output)
    with pytest.raises(ValueError):
        relocation.attest(root, sha, root / "relocation.json")
    monkeypatch.setenv("REPORTER_MODEL", "unexpected-runtime-model")
    with pytest.raises(ValueError, match="observed runtime changed"):
        relocation.verify_record(output, digest_value)


@pytest.mark.parametrize("field", ["files", "packages", "python", "pricing_sha256"])
def test_observed_runtime_drift_rejected(imported, tmp_path, monkeypatch, field):
    root, sha, _ = imported
    output = tmp_path / "relocation.json"
    record, expected = relocation.attest(root, sha, output)
    original = relocation.runtime_freeze

    def drift(path):
        result = original(path)
        if path == record.bindings.runtime_root:
            value = (
                {"unreviewed": "0" * 64} if field in {"files", "packages"} else "0" * 64
            )
            return result.model_copy(update={field: value})
        return result

    monkeypatch.setattr(relocation, "runtime_freeze", drift)
    with pytest.raises(ValueError, match="observed runtime changed"):
        relocation.verify_record(output, expected)


def test_record_tampering_and_asset_changes_rejected(imported, tmp_path):
    root, sha, _ = imported
    output = tmp_path / "relocation.json"
    _, expected = relocation.attest(root, sha, output)
    verified = relocation.verify_import(root, sha)
    with pytest.raises(ValueError):
        verified.asset_path("undeclared")
    (root / "data/snapshots/one.sqlite").write_bytes(b"changed after validation")
    with pytest.raises(ValueError):
        verified.asset_path("snapshots/one.sqlite")
    output.write_text(output.read_text().replace("offline_inspection_only", "execute"))
    with pytest.raises(ValueError):
        relocation.verify_record(output, expected)


@pytest.mark.parametrize("status", ["failed", "running"])
def test_nonterminal_or_failed_boundary_never_becomes_a_retry(imported, status):
    root, _, campaign = imported
    generations = root / "evidence/tables/reporting.generations.json"
    rows = read(generations)
    rows[0]["status"] = status
    rows[0]["submitted_artifact_version_id"] = None
    write_json(generations, rows)
    revisions = root / "evidence/tables/memory.memory_revisions.json"
    write_json(revisions, read(revisions)[:1])
    head = root / "evidence/tables/memory.current_revisions.json"
    rows = read(head)
    rows[0]["current_revision_id"] = str(campaign.root_revision_id)
    write_json(head, rows)
    (root / "campaign/indexing/one/receipt.json").unlink()
    verified = relocation.verify_import(root, seal(root))
    assert verified.next_step == 0
    assert verified.summary()["retained_next_status"] == status
    assert verified.progress.steps[0].attempts == 1
    assert verified.summary()["execution_authorized"] is False


@pytest.mark.parametrize("mutation", ["bindings", "adapter", "platform"])
def test_separately_attested_bindings_and_adapter_reject_drift(
    imported, tmp_path, monkeypatch, mutation
):
    root, sha, _ = imported
    output = tmp_path / "relocation.json"
    record, expected = relocation.attest(root, sha, output)
    if mutation == "bindings":
        value = read(output)
        value["bindings"]["data_root"] = str(tmp_path / "other-data")
        write_json(output, value)
        expected = digest(output.read_bytes())
    elif mutation == "platform":
        monkeypatch.setattr(relocation.platform, "release", lambda: "changed-kernel")
    else:
        original = relocation.runtime_freeze

        def changed(path):
            result = original(path)
            if path != record.bindings.runtime_root:
                return result.model_copy(update={"files": {"changed.py": "0" * 64}})
            return result

        monkeypatch.setattr(relocation, "runtime_freeze", changed)
    with pytest.raises(ValueError, match="observed runtime changed"):
        relocation.verify_record(output, expected)


def test_duplicate_json_keys_and_unknown_versions_fail_closed(imported):
    root, sha, _ = imported
    with pytest.raises(ValueError, match="duplicate JSON"):
        relocation.parse_json(b'{"same": 1, "same": 2}')
    path = root / "transfer-manifest.json"
    value = read(path)
    value["schema_version"] = 2
    write_json(path, value)
    with pytest.raises(ValueError):
        relocation.verify_import(root, digest(path.read_bytes()))


def test_cli_failure_does_not_echo_private_inputs(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"private": "never-print-this-value"}')
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.season_simulation.relocation",
            "verify",
            "--record",
            str(bad),
            "--record-sha256",
            digest(bad.read_bytes()),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "never-print-this-value" not in result.stderr
    assert "No execution authorized" in result.stderr
