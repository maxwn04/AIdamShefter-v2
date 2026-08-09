from __future__ import annotations

import json
from typing import cast
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine

from backend.cli import memory
from backend.config import DatabaseSettings
from backend.resources.memory.errors import MemoryNotFound
from backend.resources.memory.objects import RebuildResult, SearchIndexStatus


class FakeAdmin:
    def __init__(self) -> None:
        self.status_calls: list[UUID] = []
        self.rebuild_calls: list[UUID] = []

    def search_index_status(self, competition_id: UUID) -> SearchIndexStatus:
        self.status_calls.append(competition_id)
        return SearchIndexStatus(
            competition_id=competition_id,
            builder_version=3,
            canonical_version_count=10,
            indexed_document_count=8,
            missing_document_count=1,
            stale_document_count=1,
        )

    def rebuild_search_index(self, competition_id: UUID) -> RebuildResult:
        self.rebuild_calls.append(competition_id)
        return RebuildResult(
            competition_id=competition_id,
            builder_version=3,
            rebuilt_document_count=10,
        )


def test_status_outputs_only_status_contract_fields() -> None:
    competition_id = uuid4()
    admin = FakeAdmin()

    result = memory.run(memory.parse_args(["status", str(competition_id)]), admin)
    output = memory.format_result(result)

    assert json.loads(output) == {
        "builder_version": 3,
        "canonical_version_count": 10,
        "competition_id": str(competition_id),
        "indexed_document_count": 8,
        "missing_document_count": 1,
        "stale_document_count": 1,
    }
    assert admin.status_calls == [competition_id]
    assert admin.rebuild_calls == []


def test_rebuild_uses_manager_owned_batching_and_outputs_result() -> None:
    competition_id = uuid4()
    admin = FakeAdmin()

    result = memory.run(
        memory.parse_args(["rebuild", str(competition_id)]),
        admin,
    )
    output = memory.format_result(result)

    assert json.loads(output) == {
        "builder_version": 3,
        "competition_id": str(competition_id),
        "rebuilt_document_count": 10,
    }
    assert admin.rebuild_calls == [competition_id]
    assert admin.status_calls == []


def test_invalid_identifier_fails_at_argparse_boundary() -> None:
    admin = FakeAdmin()

    with pytest.raises(SystemExit) as exc_info:
        memory.parse_args(["status", "not-a-uuid"])

    assert exc_info.value.code == 2
    assert admin.status_calls == []
    assert admin.rebuild_calls == []


def test_main_builds_one_manager_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    competition_id = uuid4()
    settings = DatabaseSettings(
        runtime_url="postgresql+psycopg://aidam_runtime:secret@localhost/aidam",
        migration_url=None,
        ca_file=None,
        pool_size=2,
        max_overflow=2,
        statement_timeout_ms=30_000,
        require_tls=False,
    )
    engine = Mock(spec=Engine)
    session_factory = object()
    admin = FakeAdmin()
    manager_factory = Mock(return_value=admin)
    engine_factory = Mock(return_value=engine)

    monkeypatch.setattr(
        memory.DatabaseSettings,
        "from_environment",
        Mock(return_value=settings),
    )
    monkeypatch.setattr(memory, "build_runtime_engine", engine_factory)
    monkeypatch.setattr(
        memory,
        "create_session_factory",
        Mock(return_value=session_factory),
    )
    monkeypatch.setattr(memory, "MemoryManager", manager_factory)

    assert memory.main(["status", str(competition_id)]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "builder_version": 3,
        "canonical_version_count": 10,
        "competition_id": str(competition_id),
        "indexed_document_count": 8,
        "missing_document_count": 1,
        "stale_document_count": 1,
    }
    engine_settings = engine_factory.call_args.args[0]
    assert engine_settings.application_name == "aidam-memory"
    manager_factory.assert_called_once_with(session_factory)
    cast(Mock, engine.dispose).assert_called_once_with()


def test_main_formats_expected_memory_error_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    competition_id = uuid4()
    settings = DatabaseSettings(
        runtime_url="postgresql+psycopg://aidam_runtime:secret@localhost/aidam",
        migration_url=None,
        ca_file=None,
        pool_size=2,
        max_overflow=2,
        statement_timeout_ms=30_000,
        require_tls=False,
    )
    engine = Mock(spec=Engine)
    admin = FakeAdmin()
    admin.search_index_status = Mock(
        side_effect=MemoryNotFound("canonical memory competition not found")
    )

    monkeypatch.setattr(
        memory.DatabaseSettings,
        "from_environment",
        Mock(return_value=settings),
    )
    monkeypatch.setattr(memory, "build_runtime_engine", Mock(return_value=engine))
    monkeypatch.setattr(memory, "create_session_factory", Mock(return_value=object()))
    monkeypatch.setattr(memory, "MemoryManager", Mock(return_value=admin))

    assert memory.main(["status", str(competition_id)]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "error": {
            "code": "memory_not_found",
            "details": {},
            "message": "canonical memory competition not found",
        }
    }
    cast(Mock, engine.dispose).assert_called_once_with()
