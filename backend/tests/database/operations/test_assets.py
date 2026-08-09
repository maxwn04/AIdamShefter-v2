from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Engine

from infra.database import common

ROOT = Path(__file__).resolve().parents[4]


def test_hosted_role_bootstrap_does_not_duplicate_application_ddl() -> None:
    bootstrap = (ROOT / "infra" / "database" / "bootstrap_roles.sql").read_text()
    uppercase = bootstrap.upper()

    assert "CREATE SCHEMA" not in uppercase
    assert "CREATE TABLE" not in uppercase
    assert "CREATE ROLE AIDAM_OWNER" in uppercase
    assert "CREATE ROLE AIDAM_RUNTIME" in uppercase
    assert "REVOKE CREATE ON SCHEMA PUBLIC FROM PUBLIC" in uppercase
    assert "GRANT USAGE, CREATE ON SCHEMA PUBLIC TO AIDAM_OWNER" in uppercase
    assert "SET SEARCH_PATH = PG_CATALOG" in uppercase


def test_hosted_workflow_cannot_target_production() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "database-hosted-verify.yml"
    ).read_text()

    assert "- preview" in workflow
    assert "- staging" in workflow
    assert "- production" not in workflow
    assert "cancel-in-progress: false" in workflow
    assert "alembic -c backend/migrations/alembic.ini check" in workflow
    assert "infra.database.verify_database" in workflow


def test_database_ci_tracks_all_operational_hardening_paths() -> None:
    workflow = (ROOT / ".github" / "workflows" / "database.yml").read_text()

    assert '"infra/database/**"' in workflow
    assert '"docs/database/runbooks/**"' in workflow
    assert '".github/workflows/database-hosted-verify.yml"' in workflow


def test_backup_and_restore_scripts_have_tls_and_target_guards() -> None:
    backup = (ROOT / "infra" / "database" / "backup.sh").read_text()
    restore = (ROOT / "infra" / "database" / "restore_drill.sh").read_text()

    assert "PGSSLMODE=verify-full" in backup
    assert "refusing to overwrite" in backup
    assert "--role aidam_owner" in backup
    assert "--schema core" in backup
    assert "--table public.alembic_version" in backup
    assert "printf '%s\\n' \"$application_hash\"" in backup
    assert "PGSSLMODE=verify-full" in restore
    assert "aidam_restore_*" in restore
    assert "AIDAM_RESTORE_CONFIRM_DATABASE" in restore
    assert "restore target is not empty" in restore
    assert "--single-transaction" in restore
    assert "shasum -a 256 --check" not in restore
    assert 'verify_checksum "$backup_path" "$backup_path.sha256"' in restore
    assert (
        'verify_checksum "$version_backup_path" '
        '"$version_backup_path.sha256"'
    ) in restore


def test_foundation_revision_freezes_its_schema_set() -> None:
    revision = (
        ROOT / "backend" / "migrations" / "versions" / "0001_database_foundation.py"
    ).read_text()

    assert "from backend.database.base import APPLICATION_SCHEMAS" not in revision
    assert '_APPLICATION_SCHEMAS = ("core", "sleeper", "memory", "reporting")' in revision


def test_verified_engine_forces_ca_and_verify_full(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ca_file = tmp_path / "root.crt"
    _ = ca_file.write_text("test certificate fixture")
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://aidam_api:secret@database.example/aidam",
    )
    monkeypatch.setenv("AIDAM_DATABASE_CA_FILE", str(ca_file))
    captured: dict[str, object] = {}
    expected_engine = cast(Engine, object())

    def fake_create_engine(url: str, **kwargs: object) -> Engine:
        captured["url"] = url
        captured.update(kwargs)
        return expected_engine

    monkeypatch.setattr(common, "create_engine", fake_create_engine)

    result = common.create_verified_engine("TEST_DATABASE_URL", "aidam-verify")

    assert result is expected_engine
    connect_args = cast(dict[str, str | int], captured["connect_args"])
    assert connect_args["sslmode"] == "verify-full"
    assert connect_args["sslrootcert"] == str(ca_file)
    assert connect_args["application_name"] == "aidam-verify"


def test_verified_engine_rejects_missing_ca(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://aidam_api:secret@database.example/aidam",
    )
    monkeypatch.delenv("AIDAM_DATABASE_CA_FILE", raising=False)

    with pytest.raises(RuntimeError, match="AIDAM_DATABASE_CA_FILE is required"):
        _ = common.create_verified_engine("TEST_DATABASE_URL", "aidam-verify")
