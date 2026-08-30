from collections.abc import Mapping
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError, IntegrityError

from backend.database.models.core import Competition, CompetitionSeason
from backend.database.models.memory import MemoryRevision
from backend.database.models.reporting import (
    AICall,
    Artifact,
    ArtifactVersion,
    EvaluationWorkspace,
    Generation,
    ToolCall,
)


def _seed_domain(connection: Connection, label: str) -> dict[str, UUID]:
    competition_id = uuid4()
    season_id = uuid4()
    revision_id = uuid4()
    connection.execute(
        sa.insert(Competition),
        {"id": competition_id, "display_name": f"{label} Competition"},
    )
    connection.execute(
        sa.insert(CompetitionSeason),
        {
            "id": season_id,
            "competition_id": competition_id,
            "season_year": 2026,
            "sequence_number": 1,
            "sleeper_league_id": f"league-{uuid4()}",
        },
    )
    connection.execute(
        sa.insert(MemoryRevision),
        {
            "id": revision_id,
            "competition_id": competition_id,
            "sequence_number": 0,
            "competition_season_id": season_id,
            "state_content_hash": f"state-{uuid4()}",
        },
    )
    return {
        "competition": competition_id,
        "season": season_id,
        "revision": revision_id,
    }


def _generation_values(
    domain: Mapping[str, UUID],
    *,
    status: str = "pending",
    generation_id: UUID | None = None,
    **overrides: object,
) -> dict[str, object]:
    values: dict[str, object] = {
        "id": generation_id or uuid4(),
        "competition_id": domain["competition"],
        "competition_season_id": domain["season"],
        "kind": "live",
        "status": status,
        "request_text": "write the report",
        "requested_primary_model": "test-model",
        "settings_jsonb": {},
        "current_turn": 0,
    }
    values.update(overrides)
    return values


def _ai_call_values(
    generation_id: UUID,
    *,
    status: str = "started",
    call_id: UUID | None = None,
    turn_number: int = 1,
    attempt_number: int = 0,
) -> dict[str, object]:
    return {
        "id": call_id or uuid4(),
        "generation_id": generation_id,
        "turn_number": turn_number,
        "attempt_number": attempt_number,
        "requested_model": "test-model",
        "input_messages": [],
        "tool_definitions": [],
        "request_parameters": {},
        "status": status,
    }


def _tool_call_values(
    generation_id: UUID,
    ai_call_id: UUID,
    *,
    status: str = "started",
    tool_call_id: UUID | None = None,
    ordinal: int = 0,
) -> dict[str, object]:
    return {
        "id": tool_call_id or uuid4(),
        "generation_id": generation_id,
        "ai_call_id": ai_call_id,
        "tool_ordinal": ordinal,
        "tool_name": "lookup",
        "implementation_version": "v1",
        "arguments_jsonb": {},
        "status": status,
    }


def _artifact_values(
    generation_id: UUID,
    *,
    artifact_id: UUID | None = None,
    path: str = "article.md",
) -> dict[str, object]:
    return {
        "id": artifact_id or uuid4(),
        "generation_id": generation_id,
        "path": path,
        "media_type": "text/markdown",
    }


def _artifact_version_values(
    artifact_id: UUID,
    generation_id: UUID,
    *,
    version_id: UUID | None = None,
    revision_number: int = 1,
    source_ai_call_id: UUID | None = None,
    source_tool_call_id: UUID | None = None,
) -> dict[str, object]:
    return {
        "id": version_id or uuid4(),
        "artifact_id": artifact_id,
        "generation_id": generation_id,
        "revision_number": revision_number,
        "content": "report body",
        "content_hash": f"hash-{uuid4()}",
        "source_ai_call_id": source_ai_call_id,
        "source_tool_call_id": source_tool_call_id,
    }


def _assert_integrity_error(engine: Engine, statement: sa.Executable) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(statement)


def _assert_database_error(engine: Engine, statement: sa.Executable) -> None:
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(statement)


def test_reporting_schema_has_only_structural_checks_and_history_guards(
    database_engine: Engine,
) -> None:
    expected_tables = {
        "generations",
        "evaluation_workspaces",
        "ai_calls",
        "tool_calls",
        "artifacts",
        "artifact_versions",
        "generation_memory_recalls",
    }
    expected_checks = {
        "ck_artifacts_finalization_shape",
        "ck_generations_submitted_artifact_shape",
        "ck_generations_workspace_shape",
        "ck_generations_unambiguous_memory_input",
        "ck_generation_memory_recalls_status",
    }
    expected_partial_uniques = {
        "uq_evaluation_workspaces_one_active",
        "uq_ai_calls_one_success_per_turn",
    }
    expected_triggers = {
        "generations_protect_terminal",
        "generations_protect_workspace_membership",
        "evaluation_workspaces_protect_history",
        "ai_calls_protect_terminal",
        "tool_calls_protect_terminal",
        "artifact_versions_append_only",
        "artifacts_protect_identity_and_finalization",
        "generation_memory_recalls_append_only",
    }

    with database_engine.connect() as connection:
        tables = set(
            connection.execute(
                sa.text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'reporting'"
                )
            ).scalars()
        )
        checks = set(
            connection.execute(
                sa.text(
                    """
                    SELECT constraint_record.conname
                    FROM pg_catalog.pg_constraint AS constraint_record
                    JOIN pg_catalog.pg_namespace AS namespace
                      ON namespace.oid = constraint_record.connamespace
                    WHERE namespace.nspname = 'reporting'
                      AND constraint_record.contype = 'c'
                    """
                )
            ).scalars()
        )
        partial_uniques = set(
            connection.execute(
                sa.text(
                    """
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = 'reporting'
                      AND indexdef LIKE 'CREATE UNIQUE INDEX%WHERE%'
                    """
                )
            ).scalars()
        )
        indexes = set(
            connection.execute(
                sa.text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'reporting'"
                )
            ).scalars()
        )
        triggers = set(
            connection.execute(
                sa.text(
                    """
                    SELECT trigger_name
                    FROM information_schema.triggers
                    WHERE trigger_schema = 'reporting'
                    """
                )
            ).scalars()
        )
        delete_rules = set(
            connection.execute(
                sa.text(
                    """
                    SELECT delete_rule
                    FROM information_schema.referential_constraints
                    WHERE constraint_schema = 'reporting'
                    """
                )
            ).scalars()
        )
        identifiers = list(
            connection.execute(
                sa.text(
                    """
                    SELECT constraint_name
                    FROM information_schema.table_constraints
                    WHERE constraint_schema = 'reporting'
                    UNION ALL
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = 'reporting'
                    """
                )
            ).scalars()
        )

    assert tables == expected_tables
    assert checks == expected_checks
    assert expected_partial_uniques <= partial_uniques
    assert "ix_generations_competition_submitted_completed" in indexes
    assert expected_triggers <= triggers
    assert delete_rules == {"RESTRICT"}
    assert all(len(identifier) <= 63 for identifier in identifiers)
    assert not any("ck_generations_ck_generations" in name for name in checks)


def test_generation_scope_and_memory_input_shape_are_enforced(
    database_engine: Engine,
) -> None:
    with database_engine.begin() as connection:
        first = _seed_domain(connection, "First")
        second = _seed_domain(connection, "Second")
        workspace_id = uuid4()
        connection.execute(
            sa.insert(EvaluationWorkspace),
            {
                "id": workspace_id,
                "competition_id": first["competition"],
                "base_memory_revision_id": first["revision"],
                "status": "active",
            },
        )

    _assert_integrity_error(
        database_engine,
        sa.insert(Generation).values(
            **_generation_values(
                first,
                competition_season_id=second["season"],
            )
        ),
    )
    _assert_integrity_error(
        database_engine,
        sa.insert(Generation).values(
            **_generation_values(
                second,
                evaluation_workspace_id=workspace_id,
                workspace_sequence_number=1,
            )
        ),
    )
    _assert_integrity_error(
        database_engine,
        sa.insert(Generation).values(
            **_generation_values(first, workspace_sequence_number=1)
        ),
    )
    _assert_integrity_error(
        database_engine,
        sa.insert(Generation).values(
            **_generation_values(
                first,
                input_memory_revision_id=first["revision"],
                input_memory_artifact_version_id=uuid4(),
            )
        ),
    )


def test_reporting_accepts_application_owned_semantics(
    database_engine: Engine,
) -> None:
    generation_id = uuid4()
    call_id = uuid4()
    with database_engine.begin() as connection:
        domain = _seed_domain(connection, "Semantic Boundary")
        connection.execute(
            sa.insert(Generation),
            _generation_values(
                domain,
                generation_id=generation_id,
                status="future_generation_status",
                kind="future_kind",
                current_turn=-10,
                week_start=-4,
                week_end=-99,
                manifest_hash="",
            ),
        )
        connection.execute(
            sa.insert(AICall),
            _ai_call_values(
                generation_id,
                call_id=call_id,
                status="future_call_status",
                turn_number=-3,
                attempt_number=-2,
            ),
        )
        connection.execute(
            sa.insert(ToolCall),
            _tool_call_values(
                generation_id,
                call_id,
                status="future_tool_status",
                ordinal=-1,
            ),
        )


def test_partial_unique_indexes_and_natural_identity(
    database_engine: Engine,
) -> None:
    with database_engine.begin() as connection:
        domain = _seed_domain(connection, "Concurrency")
        first_workspace = uuid4()
        connection.execute(
            sa.insert(EvaluationWorkspace),
            {
                "id": first_workspace,
                "competition_id": domain["competition"],
                "base_memory_revision_id": domain["revision"],
                "status": "active",
            },
        )
        generation_id = uuid4()
        connection.execute(
            sa.insert(Generation),
            _generation_values(domain, generation_id=generation_id),
        )
        connection.execute(
            sa.insert(AICall),
            _ai_call_values(
                generation_id,
                status="succeeded",
                turn_number=1,
                attempt_number=0,
            ),
        )
        artifact_id = uuid4()
        connection.execute(
            sa.insert(Artifact),
            _artifact_values(generation_id, artifact_id=artifact_id),
        )
        connection.execute(
            sa.insert(ArtifactVersion),
            _artifact_version_values(
                artifact_id,
                generation_id,
                revision_number=1,
            ),
        )

    _assert_integrity_error(
        database_engine,
        sa.insert(EvaluationWorkspace).values(
            id=uuid4(),
            competition_id=domain["competition"],
            base_memory_revision_id=domain["revision"],
            status="active",
        ),
    )
    _assert_integrity_error(
        database_engine,
        sa.insert(AICall).values(
            **_ai_call_values(
                generation_id,
                status="succeeded",
                turn_number=1,
                attempt_number=1,
            )
        ),
    )
    _assert_integrity_error(
        database_engine,
        sa.insert(Artifact).values(
            **_artifact_values(generation_id, path="article.md")
        ),
    )

    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(EvaluationWorkspace),
            {
                "id": uuid4(),
                "competition_id": domain["competition"],
                "base_memory_revision_id": domain["revision"],
                "status": "discarded",
            },
        )
        connection.execute(
            sa.insert(AICall),
            _ai_call_values(
                generation_id,
                status="retryable_error",
                turn_number=1,
                attempt_number=1,
            ),
        )
        connection.execute(
            sa.insert(ArtifactVersion),
            _artifact_version_values(
                artifact_id,
                generation_id,
                revision_number=2,
            ),
        )


def test_tool_and_artifact_provenance_cannot_cross_generations(
    database_engine: Engine,
) -> None:
    first_generation = uuid4()
    second_generation = uuid4()
    first_ai_call = uuid4()
    second_artifact = uuid4()
    with database_engine.begin() as connection:
        domain = _seed_domain(connection, "Provenance")
        connection.execute(
            sa.insert(Generation),
            [
                _generation_values(domain, generation_id=first_generation),
                _generation_values(domain, generation_id=second_generation),
            ],
        )
        connection.execute(
            sa.insert(AICall),
            _ai_call_values(first_generation, call_id=first_ai_call),
        )
        connection.execute(
            sa.insert(Artifact),
            _artifact_values(second_generation, artifact_id=second_artifact),
        )

    _assert_integrity_error(
        database_engine,
        sa.insert(ToolCall).values(
            **_tool_call_values(second_generation, first_ai_call)
        ),
    )
    _assert_integrity_error(
        database_engine,
        sa.insert(ArtifactVersion).values(
            **_artifact_version_values(
                second_artifact,
                second_generation,
                source_ai_call_id=first_ai_call,
            )
        ),
    )


@pytest.mark.parametrize(
    ("table", "status"),
    [
        (Generation, "succeeded"),
        (AICall, "succeeded"),
        (ToolCall, "succeeded"),
    ],
)
def test_terminal_execution_history_is_immutable(
    database_engine: Engine,
    table: type[Generation] | type[AICall] | type[ToolCall],
    status: str,
) -> None:
    row_id = uuid4()
    with database_engine.begin() as connection:
        domain = _seed_domain(connection, f"Terminal {table.__name__}")
        generation_id = row_id if table is Generation else uuid4()
        connection.execute(
            sa.insert(Generation),
            _generation_values(
                domain,
                generation_id=generation_id,
                status=status if table is Generation else "pending",
            ),
        )
        if table is AICall:
            connection.execute(
                sa.insert(AICall),
                _ai_call_values(generation_id, call_id=row_id, status=status),
            )
        elif table is ToolCall:
            ai_call_id = uuid4()
            connection.execute(
                sa.insert(AICall),
                _ai_call_values(generation_id, call_id=ai_call_id),
            )
            connection.execute(
                sa.insert(ToolCall),
                _tool_call_values(
                    generation_id,
                    ai_call_id,
                    tool_call_id=row_id,
                    status=status,
                ),
            )

    _assert_database_error(
        database_engine,
        sa.update(table).where(table.id == row_id).values(status="reopened"),
    )
    _assert_database_error(
        database_engine,
        sa.delete(table).where(table.id == row_id),
    )


def test_artifact_versions_are_append_only(database_engine: Engine) -> None:
    version_id = uuid4()
    with database_engine.begin() as connection:
        domain = _seed_domain(connection, "Append Only")
        generation_id = uuid4()
        artifact_id = uuid4()
        connection.execute(
            sa.insert(Generation),
            _generation_values(domain, generation_id=generation_id),
        )
        connection.execute(
            sa.insert(Artifact),
            _artifact_values(generation_id, artifact_id=artifact_id),
        )
        connection.execute(
            sa.insert(ArtifactVersion),
            _artifact_version_values(
                artifact_id,
                generation_id,
                version_id=version_id,
            ),
        )

    _assert_database_error(
        database_engine,
        sa.update(ArtifactVersion)
        .where(ArtifactVersion.id == version_id)
        .values(content="rewritten"),
    )
    _assert_database_error(
        database_engine,
        sa.delete(ArtifactVersion).where(ArtifactVersion.id == version_id),
    )


def test_artifact_identity_and_finalization_are_immutable(
    database_engine: Engine,
) -> None:
    with database_engine.begin() as connection:
        domain = _seed_domain(connection, "Finalized Artifact")
        generation_id = uuid4()
        artifact_id = uuid4()
        version_id = uuid4()
        connection.execute(
            sa.insert(Generation),
            _generation_values(domain, generation_id=generation_id),
        )
        connection.execute(
            sa.insert(Artifact),
            _artifact_values(generation_id, artifact_id=artifact_id),
        )
        connection.execute(
            sa.insert(ArtifactVersion),
            _artifact_version_values(
                artifact_id,
                generation_id,
                version_id=version_id,
            ),
        )
        connection.execute(
            sa.update(Artifact)
            .where(Artifact.id == artifact_id)
            .values(
                finalized_version_id=version_id,
                finalized_at=sa.func.now(),
            )
        )

    _assert_database_error(
        database_engine,
        sa.update(Artifact)
        .where(Artifact.id == artifact_id)
        .values(path="renamed.md"),
    )
    _assert_database_error(
        database_engine,
        sa.update(Artifact)
        .where(Artifact.id == artifact_id)
        .values(finalized_version_id=None, finalized_at=None),
    )
    _assert_database_error(
        database_engine,
        sa.delete(Artifact).where(Artifact.id == artifact_id),
    )
    _assert_database_error(
        database_engine,
        sa.insert(ArtifactVersion).values(
            **_artifact_version_values(
                artifact_id,
                generation_id,
                revision_number=2,
            )
        ),
    )


def test_artifact_finalization_requires_its_latest_version(
    database_engine: Engine,
) -> None:
    with database_engine.begin() as connection:
        domain = _seed_domain(connection, "Finalization Scope")
        generation_id = uuid4()
        first_artifact_id = uuid4()
        second_artifact_id = uuid4()
        first_version_id = uuid4()
        latest_version_id = uuid4()
        other_version_id = uuid4()
        connection.execute(
            sa.insert(Generation),
            _generation_values(domain, generation_id=generation_id),
        )
        connection.execute(
            sa.insert(Artifact),
            [
                _artifact_values(
                    generation_id,
                    artifact_id=first_artifact_id,
                    path="article.md",
                ),
                _artifact_values(
                    generation_id,
                    artifact_id=second_artifact_id,
                    path="brief.md",
                ),
            ],
        )
        connection.execute(
            sa.insert(ArtifactVersion),
            [
                _artifact_version_values(
                    first_artifact_id,
                    generation_id,
                    version_id=first_version_id,
                    revision_number=1,
                ),
                _artifact_version_values(
                    first_artifact_id,
                    generation_id,
                    version_id=latest_version_id,
                    revision_number=2,
                ),
                _artifact_version_values(
                    second_artifact_id,
                    generation_id,
                    version_id=other_version_id,
                    revision_number=1,
                ),
            ],
        )

    _assert_database_error(
        database_engine,
        sa.update(Artifact)
        .where(Artifact.id == first_artifact_id)
        .values(
            finalized_version_id=first_version_id,
            finalized_at=sa.func.now(),
        ),
    )
    _assert_database_error(
        database_engine,
        sa.update(Artifact)
        .where(Artifact.id == first_artifact_id)
        .values(
            finalized_version_id=other_version_id,
            finalized_at=sa.func.now(),
        ),
    )

    with database_engine.begin() as connection:
        connection.execute(
            sa.update(Artifact)
            .where(Artifact.id == first_artifact_id)
            .values(
                finalized_version_id=latest_version_id,
                finalized_at=sa.func.now(),
            )
        )


def test_generation_submission_requires_its_own_finalized_artifact(
    database_engine: Engine,
) -> None:
    with database_engine.begin() as connection:
        domain = _seed_domain(connection, "Submitted Output")
        source_generation_id = uuid4()
        other_generation_id = uuid4()
        artifact_id = uuid4()
        version_id = uuid4()
        connection.execute(
            sa.insert(Generation),
            [
                _generation_values(
                    domain,
                    generation_id=source_generation_id,
                    status="running",
                ),
                _generation_values(
                    domain,
                    generation_id=other_generation_id,
                    status="running",
                ),
            ],
        )
        connection.execute(
            sa.insert(Artifact),
            _artifact_values(
                source_generation_id,
                artifact_id=artifact_id,
                path="drafts/custom-name.md",
            ),
        )
        connection.execute(
            sa.insert(ArtifactVersion),
            _artifact_version_values(
                artifact_id,
                source_generation_id,
                version_id=version_id,
            ),
        )
        connection.execute(
            sa.update(Artifact)
            .where(Artifact.id == artifact_id)
            .values(
                finalized_version_id=version_id,
                finalized_at=sa.func.now(),
            )
        )

    _assert_integrity_error(
        database_engine,
        sa.update(Generation)
        .where(Generation.id == source_generation_id)
        .values(submitted_artifact_version_id=version_id),
    )
    _assert_integrity_error(
        database_engine,
        sa.update(Generation)
        .where(Generation.id == other_generation_id)
        .values(
            status="succeeded",
            submitted_artifact_version_id=version_id,
        ),
    )

    with database_engine.begin() as connection:
        connection.execute(
            sa.update(Generation)
            .where(Generation.id == source_generation_id)
            .values(
                status="succeeded",
                submitted_artifact_version_id=version_id,
                completed_at=sa.func.now(),
            )
        )


def test_closed_workspace_and_generation_membership_are_immutable(
    database_engine: Engine,
) -> None:
    workspace_id = uuid4()
    generation_id = uuid4()
    with database_engine.begin() as connection:
        domain = _seed_domain(connection, "Closed Workspace")
        connection.execute(
            sa.insert(EvaluationWorkspace),
            {
                "id": workspace_id,
                "competition_id": domain["competition"],
                "base_memory_revision_id": domain["revision"],
                "status": "active",
            },
        )
        connection.execute(
            sa.insert(Generation),
            _generation_values(
                domain,
                generation_id=generation_id,
                evaluation_workspace_id=workspace_id,
                workspace_sequence_number=1,
            ),
        )
        connection.execute(
            sa.update(EvaluationWorkspace)
            .where(EvaluationWorkspace.id == workspace_id)
            .values(status="discarded")
        )

    _assert_database_error(
        database_engine,
        sa.update(EvaluationWorkspace)
        .where(EvaluationWorkspace.id == workspace_id)
        .values(status="active"),
    )
    _assert_database_error(
        database_engine,
        sa.update(Generation)
        .where(Generation.id == generation_id)
        .values(evaluation_workspace_id=None, workspace_sequence_number=None),
    )
    _assert_database_error(
        database_engine,
        sa.insert(Generation).values(
            **_generation_values(
                domain,
                evaluation_workspace_id=workspace_id,
                workspace_sequence_number=2,
            )
        ),
    )
