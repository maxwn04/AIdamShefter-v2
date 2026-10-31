"""Synthetic evidence only: no private exports, database or provider calls."""

import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
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
from scripts import verify_campaign_import as verifier
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
        raise AssertionError("offline verification attempted network access")

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


def test_verification_preserves_originals_and_reports_differences(imported):
    root, sha, _ = imported
    before = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    report = verifier.verify_import(root, sha)
    assert report["next_week"] == 2
    assert report["retained_generations"] == 1
    assert report["retained_head_has_index_receipt"] is True
    assert report["scope"] == "retained_files_only"
    assert report["live_state_verified"] is False
    assert report["runtime_differences"]["packages"]["synthetic"] == {
        "frozen": "1",
        "current": None,
    }
    assert {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


def test_configuration_differences_do_not_print_values(imported, monkeypatch):
    root, sha, _ = imported
    monkeypatch.setenv("OPENAI_BASE_URL", "https://private-setting.invalid")
    report = verifier.verify_import(root, sha)
    assert "OPENAI_BASE_URL" in report["runtime_differences"]["configuration"]
    assert "private-setting" not in json.dumps(report)
    assert report["runtime_differences"]["pricing_sha256"]["frozen"] == digest(b"{}")


@pytest.mark.parametrize(
    "relative", ["../escape", "/tmp/escape", "C:\\data", "a//b", "./a", "a/../b", ""]
)
def test_paths_must_be_canonical_and_contained(tmp_path, relative):
    with pytest.raises(ValueError):
        verifier.safe_file(tmp_path, relative)


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
        verifier.verify_import(root, sha)


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
        verifier.verify_import(root, seal(root))


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
    verified = verifier.verify_import(root, seal(root))
    assert verified["next_week"] == 1
    assert verified["retained_next_status"] == status
    assert read(root / "campaign/progress.json")["steps"][0]["attempts"] == 1
    assert verified["live_state_verified"] is False


def test_duplicate_json_keys_and_unknown_versions_fail_closed(imported):
    root, sha, _ = imported
    with pytest.raises(ValueError, match="duplicate JSON"):
        verifier.parse_json(b'{"same": 1, "same": 2}')
    path = root / "transfer-manifest.json"
    value = read(path)
    value["schema_version"] = 2
    write_json(path, value)
    with pytest.raises(ValueError):
        verifier.verify_import(root, digest(path.read_bytes()))


def test_cli_failure_does_not_echo_private_inputs(tmp_path):
    bad = tmp_path / "transfer-manifest.json"
    bad.write_text('{"private": "never-print-this-value"}')
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.verify_campaign_import",
            "--import-root",
            str(tmp_path),
            "--manifest-sha256",
            digest(bad.read_bytes()),
        ],
        env={
            **os.environ,
            "PYTHON_DOTENV_DISABLED": "1",
            "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "never-print-this-value" not in result.stderr
    assert "No files changed" in result.stderr


def test_cli_verifies_with_network_blocked_before_imports(imported, tmp_path):
    root, sha, _ = imported
    attempts = tmp_path / "network-attempted"
    launcher = """
import pathlib, runpy, socket, sys
attempts = pathlib.Path(sys.argv.pop(1))
def deny(*args, **kwargs):
    attempts.write_text('blocked')
    raise AssertionError('network forbidden')
socket.socket.connect = deny
socket.create_connection = deny
runpy.run_module('scripts.verify_campaign_import', run_name='__main__')
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            launcher,
            str(attempts),
            "--import-root",
            str(root),
            "--manifest-sha256",
            sha,
        ],
        env={
            **os.environ,
            "PYTHON_DOTENV_DISABLED": "1",
            "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["next_week"] == 2
    assert not attempts.exists()
