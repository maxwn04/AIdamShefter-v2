from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import socket

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from backend.season_simulation import bootstrap, docker
from backend.services.datalayer.canonical_json import canonical_json_bytes
from backend.services.datalayer.sleeper.responses import SuccessfulSourceAttempt
from backend.services.datalayer.sleeper.scope import EndpointKind
from backend.tests.database.conftest import _alembic_config, database_url


def test_existing_target_and_occupied_port_fail_without_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(docker, "_docker", lambda *args, **kw: b"aidam-season-existing\n")
    with pytest.raises(FileExistsError):
        docker.create_target(name="aidam-season-existing", output_root=tmp_path / ".context" / "new")
    assert not (tmp_path / ".context").exists()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        with pytest.raises(OSError):
            docker.assert_free_port(listener.getsockname()[1])


def test_target_identity_and_loopback_are_required(tmp_path, monkeypatch):
    target = docker.DockerTarget("aidam-season-test", "identity", "original", 55441, "aidam", "env", str(tmp_path))
    inspected = {"Id": "replacement", "Config": {"Labels": {docker.LABEL: "identity"}}, "State": {"Running": True}, "HostConfig": {"PortBindings": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55441"}]}}}
    monkeypatch.setattr(docker, "_docker", lambda *a, **kw: json.dumps([inspected]).encode())
    with pytest.raises(ValueError, match="identity"):
        docker.verify_target(target)
    inspected["Id"] = "original"
    docker.verify_target(target)
    inspected["HostConfig"]["PortBindings"]["5432/tcp"][0]["HostIp"] = "0.0.0.0"
    with pytest.raises(ValueError):
        docker.verify_target(target)


def test_target_environment_cannot_redirect_to_existing_database(tmp_path):
    env_file = tmp_path / "target.env"
    target = docker.DockerTarget("aidam-season-test", "id", "container", 55441, "aidam", str(env_file), str(tmp_path))
    values = {key: "postgresql+psycopg://postgres:secret@127.0.0.1:55441/aidam" for key in ("AIDAM_TEST_DATABASE_URL", "AIDAM_MIGRATION_DATABASE_URL", "AIDAM_DATABASE_URL", "AIDAM_WORKER_DATABASE_URL")}
    values["AIDAM_DATALAYER_ROOT"] = str(tmp_path / "data")
    env_file.write_text("\n".join(f"{k}={v}" for k, v in values.items()))
    assert docker.target_environment(target)["AIDAM_DATALAYER_ROOT"] == str(tmp_path / "data")
    values["AIDAM_MIGRATION_DATABASE_URL"] = "postgresql+psycopg://postgres:secret@127.0.0.1:54329/aidam"
    env_file.write_text("\n".join(f"{k}={v}" for k, v in values.items()))
    with pytest.raises(ValueError, match="isolated Docker receipt"):
        docker.target_environment(target)


def test_asset_export_is_complete_deterministic_and_detects_changed_bytes(tmp_path):
    source = tmp_path / "data"
    body = b"immutable sqlite bytes"
    digest = hashlib.sha256(body).hexdigest()
    asset = source / "snapshots" / "sha256" / digest[:2] / f"{digest}.sqlite"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(body)
    first = bootstrap.export_assets(source, tmp_path / "export")
    assert first == bootstrap.export_assets(source, tmp_path / "export")
    assert (tmp_path / "export" / first[0]["path"]).read_bytes() == body
    asset.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        bootstrap.export_assets(source, tmp_path / "export")


class ScriptedSleeperSource:
    def __init__(self, **kwargs):
        pass

    def close(self):
        pass

    def execute(self, request):
        payloads = {
            EndpointKind.LEAGUE: {"league_id": "123", "name": "Scripted season", "season": "2025", "sport": "nfl", "status": "complete", "settings": {"playoff_week_start": 15, "playoff_teams": 2, "draft_rounds": 0}, "scoring_settings": {}, "roster_positions": ["QB"]},
            EndpointKind.LEAGUE_USERS: [{"user_id": "u1", "display_name": "One"}, {"user_id": "u2", "display_name": "Two"}],
            EndpointKind.NFL_STATE: {"season": "2026", "week": 1},
            EndpointKind.PLAYER_CATALOG: {"p1": {"player_id": "p1", "full_name": "Test Player", "position": "QB"}},
            EndpointKind.LEAGUE_ROSTERS: [{"roster_id": 1, "owner_id": "u1", "players": ["p1"], "starters": ["p1"], "settings": {}}, {"roster_id": 2, "owner_id": "u2", "players": [], "starters": [], "settings": {}}],
            EndpointKind.MATCHUPS: [{"roster_id": 1, "matchup_id": 1, "points": 10, "players": ["p1"], "starters": ["p1"], "players_points": {"p1": 10}}, {"roster_id": 2, "matchup_id": 1, "points": 0, "players": [], "starters": [], "players_points": {}}],
            EndpointKind.TRANSACTIONS: [],
            EndpointKind.TRADED_PICKS: [],
            EndpointKind.WINNERS_BRACKET: [],
            EndpointKind.LOSERS_BRACKET: [],
        }
        payload = payloads[request.endpoint_kind]
        raw = canonical_json_bytes(payload)
        now = datetime.now(UTC)
        return SuccessfulSourceAttempt(endpoint=request, requested_at=now, completed_at=now, http_status=200, latency_ms=0, payload=payload, raw_sha256=hashlib.sha256(raw).hexdigest(), byte_length=len(raw), media_type="application/json")


def test_real_database_bootstrap_composes_refresh_mapping_and_frozen_snapshots(database_url, tmp_path, monkeypatch):
    """Only the free HTTP transport and external dump are scripted; SQL is real."""
    import backend.composition

    monkeypatch.delenv("AIDAM_MIGRATION_DATABASE_URL", raising=False)
    monkeypatch.setenv("AIDAM_MIGRATION_REQUIRE_TLS", "false")
    monkeypatch.setenv("AIDAM_MIGRATION_ROLE", "aidam_owner")
    command.upgrade(_alembic_config(database_url), "head")

    monkeypatch.setattr(backend.composition, "SleeperSourceClient", ScriptedSleeperSource)
    monkeypatch.setattr(bootstrap, "verify_target", lambda target: None)
    monkeypatch.setattr(bootstrap, "target_environment", lambda target: {"AIDAM_MIGRATION_DATABASE_URL": database_url})
    def export_test_dump(target, destination):
        destination.write_bytes(b"test dump transport")
        return destination
    monkeypatch.setattr(bootstrap, "dump_database", export_test_dump)
    target = docker.DockerTarget("aidam-season-test", "identity", "container", 55441, "aidam", "env", str(tmp_path))
    prepared_path = bootstrap.prepare_target(target, league_id="123", season_year=2025, first_week=1, last_week=2, first_cutoff=datetime(2025, 9, 9, 12, tzinfo=UTC), model="scripted")
    prepared = json.loads(prepared_path.read_text())
    assert [step["week"] for step in prepared["steps"]] == [1, 2]
    assert all(step["input_revision"] for step in prepared["steps"])
    assert len({step["snapshot_id"] for step in prepared["steps"]}) == 2
    assets = json.loads((tmp_path / "source-only" / "manifest.json").read_text())["assets"]
    assert len([a for a in assets if a["path"].startswith("snapshots/")]) == 2
    with create_engine(database_url).connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM core.season_rosters")).scalar_one() == 2
        assert connection.execute(text("SELECT count(*) FROM reporting.generations")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM memory.memory_revisions")).scalar_one() == 0
    prepared_path.unlink()
    with pytest.raises(ValueError, match="empty initialized database"):
        bootstrap.prepare_target(target, league_id="123", season_year=2025, first_week=1, last_week=2, first_cutoff=datetime(2025, 9, 9, 12, tzinfo=UTC), model="scripted")
