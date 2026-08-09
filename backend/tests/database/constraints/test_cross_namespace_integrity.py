from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError

from backend.database.models.core import (
    Competition,
    CompetitionSeason,
    Franchise,
    SeasonRoster,
)
from backend.database.models.memory import (
    EventVersion,
    FactVersion,
    MemoryItem,
    MemoryRevision,
    MemoryVersion,
)
from backend.database.models.reporting import (
    AICall,
    Artifact,
    ArtifactVersion,
    EvaluationWorkspace,
    Generation,
    ToolCall,
)
from backend.database.models.sleeper import (
    ApiRequest,
    DataSnapshot,
    DraftPick,
    League,
    RefreshRun,
    Transaction,
    TransactionMove,
)


def _assert_database_error(engine: Engine, statement: sa.Executable) -> None:
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(statement)


def _seed_domain(connection: Connection, label: str) -> dict[str, UUID]:
    ids = {
        "competition": uuid4(),
        "season": uuid4(),
        "franchise": uuid4(),
        "roster": uuid4(),
    }
    connection.execute(
        sa.insert(Competition),
        {"id": ids["competition"], "display_name": f"{label} Competition"},
    )
    connection.execute(
        sa.insert(CompetitionSeason),
        {
            "id": ids["season"],
            "competition_id": ids["competition"],
            "season_year": 2026,
            "sequence_number": 1,
            "sleeper_league_id": f"league-{uuid4()}",
        },
    )
    connection.execute(
        sa.insert(Franchise),
        {
            "id": ids["franchise"],
            "competition_id": ids["competition"],
            "display_name": f"{label} Franchise",
        },
    )
    connection.execute(
        sa.insert(SeasonRoster),
        {
            "id": ids["roster"],
            "competition_id": ids["competition"],
            "competition_season_id": ids["season"],
            "franchise_id": ids["franchise"],
            "sleeper_roster_id": f"roster-{uuid4()}",
        },
    )
    return ids


def _insert_revision(connection: Connection, domain: dict[str, UUID]) -> UUID:
    revision_id = uuid4()
    connection.execute(
        sa.insert(MemoryRevision),
        {
            "id": revision_id,
            "competition_id": domain["competition"],
            "competition_season_id": domain["season"],
            "sequence_number": 0,
            "state_content_hash": f"state-{uuid4()}",
        },
    )
    return revision_id


def _insert_generation(
    connection: Connection,
    domain: dict[str, UUID],
    *,
    workspace_id: UUID | None = None,
    sequence_number: int | None = None,
) -> UUID:
    generation_id = uuid4()
    connection.execute(
        sa.insert(Generation),
        {
            "id": generation_id,
            "competition_id": domain["competition"],
            "competition_season_id": domain["season"],
            "evaluation_workspace_id": workspace_id,
            "workspace_sequence_number": sequence_number,
            "kind": "test",
            "status": "pending",
            "request_text": "cross namespace test",
            "requested_primary_model": "test-model",
            "settings_jsonb": {},
            "current_turn": 0,
        },
    )
    return generation_id


def _insert_tool_call(connection: Connection, generation_id: UUID) -> UUID:
    ai_call_id = uuid4()
    tool_call_id = uuid4()
    connection.execute(
        sa.insert(AICall),
        {
            "id": ai_call_id,
            "generation_id": generation_id,
            "turn_number": 1,
            "attempt_number": 0,
            "requested_model": "test-model",
            "input_messages": [],
            "tool_definitions": [],
            "request_parameters": {},
            "status": "started",
        },
    )
    connection.execute(
        sa.insert(ToolCall),
        {
            "id": tool_call_id,
            "generation_id": generation_id,
            "ai_call_id": ai_call_id,
            "tool_ordinal": 0,
            "tool_name": "lookup",
            "implementation_version": "test",
            "arguments_jsonb": {},
            "status": "started",
        },
    )
    return tool_call_id


def _insert_memory_version(
    connection: Connection,
    domain: dict[str, UUID],
    revision_id: UUID,
    generation_id: UUID,
) -> UUID:
    item_id = uuid4()
    version_id = uuid4()
    connection.execute(
        sa.insert(MemoryItem),
        {
            "id": item_id,
            "competition_id": domain["competition"],
            "kind": "test",
        },
    )
    connection.execute(
        sa.insert(MemoryVersion),
        {
            "id": version_id,
            "item_id": item_id,
            "competition_id": domain["competition"],
            "revision_number": 1,
            "introduced_revision_id": revision_id,
            "creating_generation_id": generation_id,
        },
    )
    return version_id


def _insert_request(
    connection: Connection,
    domain: dict[str, UUID] | None,
) -> UUID:
    refresh_run_id = uuid4()
    request_id = uuid4()
    connection.execute(
        sa.insert(RefreshRun),
        {
            "id": refresh_run_id,
            "competition_id": None if domain is None else domain["competition"],
            "competition_season_id": None if domain is None else domain["season"],
            "endpoint_scope": {},
            "trigger_source": "test",
            "status": "test",
            "code_version": "test",
            "normalizer_version": "test",
        },
    )
    now = datetime.now(timezone.utc)
    connection.execute(
        sa.insert(ApiRequest),
        {
            "id": request_id,
            "refresh_run_id": refresh_run_id,
            "competition_season_id": None if domain is None else domain["season"],
            "endpoint_kind": "test",
            "scope_key": f"scope:{uuid4()}",
            "request_path": "/test",
            "request_parameters": {},
            "requested_at": now,
            "completed_at": now,
            "status": "test",
            "normalization_status": "test",
        },
    )
    return request_id


def test_memory_reporting_provenance_is_competition_and_generation_scoped(
    database_engine: Engine,
) -> None:
    with database_engine.begin() as connection:
        first = _seed_domain(connection, "First provenance")
        second = _seed_domain(connection, "Second provenance")
        first_revision = _insert_revision(connection, first)
        _insert_revision(connection, second)
        first_generation = _insert_generation(connection, first)
        second_generation = _insert_generation(connection, second)
        second_tool_call = _insert_tool_call(connection, second_generation)
        first_version = _insert_memory_version(
            connection, first, first_revision, first_generation
        )
        mismatch_item_id = uuid4()
        connection.execute(
            sa.insert(MemoryItem),
            {
                "id": mismatch_item_id,
                "competition_id": first["competition"],
                "kind": "test",
            },
        )

    _assert_database_error(
        database_engine,
        sa.insert(MemoryRevision).values(
            id=uuid4(),
            competition_id=first["competition"],
            competition_season_id=first["season"],
            sequence_number=20,
            producing_generation_id=second_generation,
            state_content_hash=f"state-{uuid4()}",
        ),
    )
    _assert_database_error(
        database_engine,
        sa.insert(MemoryVersion).values(
            id=uuid4(),
            item_id=mismatch_item_id,
            competition_id=first["competition"],
            revision_number=1,
            introduced_revision_id=first_revision,
            creating_generation_id=first_generation,
            creating_tool_call_id=second_tool_call,
        ),
    )
    _assert_database_error(
        database_engine,
        sa.insert(FactVersion).values(
            version_id=first_version,
            competition_id=first["competition"],
            claim="scoped fact",
            category="test",
            confidence="test",
            status="test",
            primary_tool_call_id=second_tool_call,
            primary_tool_call_generation_id=second_generation,
        ),
    )
    _assert_database_error(
        database_engine,
        sa.insert(EventVersion).values(
            version_id=first_version,
            competition_id=second["competition"],
            event_type="test",
            headline="event",
            summary="summary",
            salience=1,
            confidence="test",
            status="test",
        ),
    )


def test_generation_snapshot_must_match_the_exact_competition_season(
    database_engine: Engine,
) -> None:
    with database_engine.begin() as connection:
        domain = _seed_domain(connection, "Snapshot season")
        second_season_id = uuid4()
        connection.execute(
            sa.insert(CompetitionSeason),
            {
                "id": second_season_id,
                "competition_id": domain["competition"],
                "season_year": 2027,
                "sequence_number": 2,
                "sleeper_league_id": f"league-{uuid4()}",
            },
        )
        snapshot_id = uuid4()
        connection.execute(
            sa.insert(DataSnapshot),
            {
                "id": snapshot_id,
                "competition_id": domain["competition"],
                "primary_competition_season_id": domain["season"],
                "mode": "test",
                "knowledge_cutoff_at": datetime.now(timezone.utc),
                "status": "building",
                "materializer_version": "test",
                "sqlite_schema_version": "test",
                "code_version": "test",
                "completeness_warnings": [],
            },
        )

    _assert_database_error(
        database_engine,
        sa.insert(Generation).values(
            id=uuid4(),
            competition_id=domain["competition"],
            competition_season_id=second_season_id,
            data_snapshot_id=snapshot_id,
            kind="test",
            status="pending",
            request_text="same competition, wrong season",
            requested_primary_model="test-model",
            settings_jsonb={},
            current_turn=0,
        ),
    )


def test_memory_api_receipts_allow_global_and_reject_cross_competition(
    database_engine: Engine,
) -> None:
    with database_engine.begin() as connection:
        first = _seed_domain(connection, "First receipt")
        second = _seed_domain(connection, "Second receipt")
        revision = _insert_revision(connection, first)
        generation = _insert_generation(connection, first)
        global_request = _insert_request(connection, None)
        second_request = _insert_request(connection, second)
        global_version = _insert_memory_version(
            connection, first, revision, generation
        )
        cross_version = _insert_memory_version(
            connection, first, revision, generation
        )
        connection.execute(
            sa.insert(FactVersion),
            {
                "version_id": global_version,
                "competition_id": first["competition"],
                "claim": "global receipt is valid",
                "category": "test",
                "confidence": "test",
                "status": "test",
                "primary_api_request_id": global_request,
            },
        )

    _assert_database_error(
        database_engine,
        sa.insert(EventVersion).values(
            version_id=cross_version,
            competition_id=first["competition"],
            event_type="test",
            headline="event",
            summary="summary",
            salience=1,
            confidence="test",
            status="test",
            primary_api_request_id=second_request,
        ),
    )


def test_artifact_memory_inputs_and_workspace_pointer_are_scope_safe(
    database_engine: Engine,
) -> None:
    with database_engine.begin() as connection:
        domain = _seed_domain(connection, "Artifact")
        revision = _insert_revision(connection, domain)
        first_workspace = uuid4()
        second_workspace = uuid4()
        connection.execute(
            sa.insert(EvaluationWorkspace),
            [
                {
                    "id": first_workspace,
                    "competition_id": domain["competition"],
                    "base_memory_revision_id": revision,
                    "status": "test-one",
                },
                {
                    "id": second_workspace,
                    "competition_id": domain["competition"],
                    "base_memory_revision_id": revision,
                    "status": "test-two",
                },
            ],
        )
        producer = _insert_generation(
            connection, domain, workspace_id=first_workspace, sequence_number=1
        )
        artifact_id = uuid4()
        artifact_version_id = uuid4()
        connection.execute(
            sa.insert(Artifact),
            {
                "id": artifact_id,
                "generation_id": producer,
                "kind": "memory",
                "name": "memory",
                "format": "json",
            },
        )
        connection.execute(
            sa.insert(ArtifactVersion),
            {
                "id": artifact_version_id,
                "artifact_id": artifact_id,
                "generation_id": producer,
                "revision_number": 1,
                "content": "{}",
                "content_hash": f"hash-{uuid4()}",
                "status": "test",
            },
        )
        connection.execute(
            sa.update(EvaluationWorkspace)
            .where(EvaluationWorkspace.id == first_workspace)
            .values(
                current_memory_artifact_version_id=artifact_version_id,
                current_memory_artifact_generation_id=producer,
            )
        )

    _assert_database_error(
        database_engine,
        sa.insert(Generation).values(
            id=uuid4(),
            competition_id=domain["competition"],
            competition_season_id=domain["season"],
            input_memory_artifact_version_id=artifact_version_id,
            evaluation_workspace_id=second_workspace,
            workspace_sequence_number=1,
            kind="test",
            status="pending",
            request_text="missing companion",
            requested_primary_model="test-model",
            settings_jsonb={},
            current_turn=0,
        ),
    )
    _assert_database_error(
        database_engine,
        sa.insert(Generation).values(
            id=uuid4(),
            competition_id=domain["competition"],
            competition_season_id=domain["season"],
            input_memory_artifact_version_id=artifact_version_id,
            input_memory_artifact_generation_id=producer,
            evaluation_workspace_id=second_workspace,
            workspace_sequence_number=2,
            kind="test",
            status="pending",
            request_text="wrong workspace",
            requested_primary_model="test-model",
            settings_jsonb={},
            current_turn=0,
        ),
    )
    _assert_database_error(
        database_engine,
        sa.update(EvaluationWorkspace)
        .where(EvaluationWorkspace.id == second_workspace)
        .values(
            current_memory_artifact_version_id=artifact_version_id,
            current_memory_artifact_generation_id=producer,
        ),
    )


def test_sleeper_source_receipts_and_draft_moves_cannot_cross_scope(
    database_engine: Engine,
) -> None:
    with database_engine.begin() as connection:
        first = _seed_domain(connection, "First sleeper")
        second = _seed_domain(connection, "Second sleeper")
        first_request = _insert_request(connection, first)
        second_request = _insert_request(connection, second)
        transaction_id = uuid4()
        draft_pick_id = uuid4()
        connection.execute(
            sa.insert(Transaction),
            {
                "id": transaction_id,
                "competition_season_id": first["season"],
                "sleeper_transaction_id": f"transaction-{uuid4()}",
                "week": 1,
                "transaction_type": "trade",
                "settings": {},
                "metadata": {},
                "source_api_request_id": first_request,
            },
        )
        connection.execute(
            sa.insert(DraftPick),
            {
                "id": draft_pick_id,
                "competition_id": second["competition"],
                "draft_season_year": 2027,
                "round": 1,
                "original_franchise_id": second["franchise"],
                "current_franchise_id": second["franchise"],
                "source": "test",
            },
        )

    _assert_database_error(
        database_engine,
        sa.insert(League).values(
            competition_season_id=first["season"],
            source_api_request_id=second_request,
            name="wrong receipt",
            season="2026",
            scoring_settings={},
            roster_positions=[],
            provider_settings={},
        ),
    )
    _assert_database_error(
        database_engine,
        sa.insert(TransactionMove).values(
            id=uuid4(),
            transaction_id=transaction_id,
            competition_season_id=first["season"],
            competition_id=first["competition"],
            move_index=0,
            move_kind="draft_pick",
            draft_pick_id=draft_pick_id,
        ),
    )


def test_all_cross_namespace_scope_constraints_are_named_and_restrictive(
    database_engine: Engine,
) -> None:
    expected = {
        "fk_leagues_source_request_scope",
        "fk_league_users_source_request_scope",
        "fk_rosters_source_request_scope",
        "fk_roster_managers_source_request_scope",
        "fk_roster_players_source_request_scope",
        "fk_matchups_source_request_scope",
        "fk_player_performances_source_request_scope",
        "fk_transactions_source_request_scope",
        "fk_playoff_matchups_source_request_scope",
        "fk_draft_picks_source_request_scope",
        "fk_transaction_moves_draft_pick_same_competition",
        "fk_memory_revisions_generation_same_competition",
        "fk_memory_versions_generation_same_competition",
        "fk_memory_versions_tool_call_same_generation",
        "fk_fact_versions_tool_generation_same_competition",
        "fk_event_versions_tool_generation_same_competition",
        "fk_generations_input_artifact_workspace_scope",
        "fk_evaluation_workspaces_current_artifact_workspace_scope",
    }
    with database_engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                """
                SELECT constraint_name, delete_rule
                FROM information_schema.referential_constraints
                WHERE constraint_schema IN ('sleeper', 'memory', 'reporting')
                """
            )
        ).all()
    discovered = {name: delete_rule for name, delete_rule in rows}
    assert expected <= discovered.keys()
    assert {discovered[name] for name in expected} == {"RESTRICT"}


def test_api_request_required_identity_fks_close_nullable_composite_holes(
    database_engine: Engine,
) -> None:
    now = datetime.now(timezone.utc)
    _assert_database_error(
        database_engine,
        sa.insert(ApiRequest).values(
            id=uuid4(),
            refresh_run_id=uuid4(),
            endpoint_kind="global",
            scope_key=f"global:{uuid4()}",
            request_path="/global",
            request_parameters={},
            requested_at=now,
            completed_at=now,
            status="test",
            normalization_status="test",
        ),
    )
    with database_engine.begin() as connection:
        refresh_run_id = uuid4()
        connection.execute(
            sa.insert(RefreshRun),
            {
                "id": refresh_run_id,
                "endpoint_scope": {},
                "trigger_source": "test",
                "status": "test",
                "code_version": "test",
                "normalizer_version": "test",
            },
        )
    _assert_database_error(
        database_engine,
        sa.insert(ApiRequest).values(
            id=uuid4(),
            refresh_run_id=refresh_run_id,
            endpoint_kind="global",
            scope_key=f"global:{uuid4()}",
            request_path="/global",
            request_parameters={},
            requested_at=now,
            completed_at=now,
            status="test",
            payload_id=uuid4(),
            normalization_status="test",
        ),
    )
