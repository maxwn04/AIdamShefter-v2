from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import CheckConstraint, Engine, Numeric
from sqlalchemy.exc import DBAPIError

from backend.database.base import Base
from backend.database.models.core import (
    Competition,
    CompetitionSeason,
    Franchise,
    SeasonRoster,
)
from backend.database.models.sleeper import (
    ApiPayload,
    ApiRequest,
    DataSnapshot,
    DataSnapshotRequest,
    Matchup,
    NormalizedScope,
    RefreshRun,
    Roster,
    RosterManager,
    User,
)


def _hash() -> str:
    return uuid4().hex + uuid4().hex


def _assert_database_error(engine: Engine, statement: sa.Executable) -> None:
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(statement)


def _insert_competition_scope(engine: Engine) -> dict[str, UUID]:
    ids = {
        "competition": uuid4(),
        "season": uuid4(),
        "franchise": uuid4(),
        "roster": uuid4(),
    }
    with engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            {"id": ids["competition"], "display_name": "Sleeper Test League"},
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
                "display_name": "Sleeper Test Franchise",
            },
        )
        connection.execute(
            sa.insert(SeasonRoster),
            {
                "id": ids["roster"],
                "competition_id": ids["competition"],
                "competition_season_id": ids["season"],
                "franchise_id": ids["franchise"],
                "sleeper_roster_id": str(uuid4()),
            },
        )
    return ids


def _insert_request(
    engine: Engine,
    scope: dict[str, UUID],
    *,
    scope_key: str,
) -> dict[str, UUID | str]:
    now = datetime.now(timezone.utc)
    refresh_run_id = uuid4()
    payload_id = uuid4()
    api_request_id = uuid4()
    response_hash = _hash()
    with engine.begin() as connection:
        connection.execute(
            sa.insert(RefreshRun),
            {
                "id": refresh_run_id,
                "competition_id": scope["competition"],
                "competition_season_id": scope["season"],
                "endpoint_scope": {},
                "trigger_source": "test",
                "status": "test",
                "code_version": "test",
                "normalizer_version": "test",
            },
        )
        connection.execute(
            sa.insert(ApiPayload),
            {
                "id": payload_id,
                "sha256_hash": response_hash,
                "byte_length": 2,
                "media_type": "application/json",
                "storage_kind": "inline_json",
                "inline_payload": {},
            },
        )
        connection.execute(
            sa.insert(ApiRequest),
            {
                "id": api_request_id,
                "refresh_run_id": refresh_run_id,
                "competition_season_id": scope["season"],
                "endpoint_kind": "test",
                "scope_key": scope_key,
                "request_path": "/test",
                "request_parameters": {},
                "requested_at": now,
                "completed_at": now,
                "status": "test",
                "payload_id": payload_id,
                "response_sha256": response_hash,
                "normalization_status": "test",
            },
        )
    return {
        "refresh_run": refresh_run_id,
        "payload": payload_id,
        "request": api_request_id,
        "hash": response_hash,
        "scope_key": scope_key,
    }


def test_sleeper_model_contract_is_structural_and_uses_exact_scores() -> None:
    sleeper_tables = {
        name for name in Base.metadata.tables if name.startswith("sleeper.")
    }
    assert len(sleeper_tables) == 19

    checks = [
        (table_name, constraint.name)
        for table_name in sleeper_tables
        for constraint in Base.metadata.tables[table_name].constraints
        if isinstance(constraint, CheckConstraint)
    ]
    assert checks == [
        ("sleeper.api_payloads", "ck_api_payloads_exactly_one_location")
    ]

    for table_name, column_name in (
        ("sleeper.matchups", "points"),
        ("sleeper.player_performances", "points"),
        ("sleeper.rosters", "points_for"),
        ("sleeper.rosters", "points_against"),
    ):
        column_type = Base.metadata.tables[table_name].c[column_name].type
        assert isinstance(column_type, Numeric)
        assert (column_type.precision, column_type.scale) == (12, 4)


def test_api_payload_requires_exactly_one_content_location(
    database_engine: Engine,
) -> None:
    base = {
        "id": uuid4(),
        "sha256_hash": _hash(),
        "byte_length": 2,
        "media_type": "application/json",
        "storage_kind": "inline_json",
    }
    _assert_database_error(
        database_engine,
        sa.insert(ApiPayload).values(
            **base,
            inline_payload={},
            object_storage_key="payloads/also-present.json",
        ),
    )
    _assert_database_error(
        database_engine,
        sa.insert(ApiPayload).values(**(base | {"id": uuid4(), "sha256_hash": _hash()})),
    )


def test_request_and_normalized_head_provenance_is_relational(
    database_engine: Engine,
) -> None:
    first_scope = _insert_competition_scope(database_engine)
    second_scope = _insert_competition_scope(database_engine)
    first_request = _insert_request(
        database_engine, first_scope, scope_key=f"league:{uuid4()}"
    )
    second_request = _insert_request(
        database_engine,
        first_scope,
        scope_key=str(first_request["scope_key"]),
    )

    _assert_database_error(
        database_engine,
        sa.insert(ApiRequest).values(
            id=uuid4(),
            refresh_run_id=first_request["refresh_run"],
            competition_season_id=second_scope["season"],
            endpoint_kind="test",
            scope_key=f"league:{uuid4()}",
            request_path="/test",
            request_parameters={},
            requested_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            status="test",
            normalization_status="test",
        ),
    )

    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(NormalizedScope),
            {
                "scope_key": first_request["scope_key"],
                "source_api_request_id": first_request["request"],
                "response_sha256": first_request["hash"],
                "normalized_row_count": 0,
            },
        )

    _assert_database_error(
        database_engine,
        sa.update(NormalizedScope)
        .where(NormalizedScope.scope_key == first_request["scope_key"])
        .values(response_sha256=_hash()),
    )
    _assert_database_error(
        database_engine,
        sa.insert(NormalizedScope).values(
            scope_key=second_request["scope_key"],
            source_api_request_id=second_request["request"],
            response_sha256=second_request["hash"],
            normalized_row_count=0,
        ),
    )


def test_normalized_scope_keys_and_roster_ownership_are_unique(
    database_engine: Engine,
) -> None:
    scope = _insert_competition_scope(database_engine)
    request = _insert_request(database_engine, scope, scope_key=f"rosters:{uuid4()}")
    first_user = str(uuid4())
    second_user = str(uuid4())
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(User),
            [
                {
                    "sleeper_user_id": first_user,
                    "display_name": "First",
                    "metadata": {},
                    "source_api_request_id": request["request"],
                },
                {
                    "sleeper_user_id": second_user,
                    "display_name": "Second",
                    "metadata": {},
                    "source_api_request_id": request["request"],
                },
            ],
        )
        connection.execute(
            sa.insert(Roster),
            {
                "season_roster_id": scope["roster"],
                "competition_season_id": scope["season"],
                "source_api_request_id": request["request"],
                "settings": {},
                "metadata": {},
            },
        )
        connection.execute(
            sa.insert(RosterManager),
            {
                "season_roster_id": scope["roster"],
                "sleeper_user_id": first_user,
                "role": "owner",
                "source_order": 0,
                "source_api_request_id": request["request"],
            },
        )

    _assert_database_error(
        database_engine,
        sa.insert(RosterManager).values(
            season_roster_id=scope["roster"],
            sleeper_user_id=second_user,
            role="owner",
            source_order=1,
            source_api_request_id=request["request"],
        ),
    )


def test_matchup_rejects_a_roster_from_another_season(
    database_engine: Engine,
) -> None:
    first_scope = _insert_competition_scope(database_engine)
    second_scope = _insert_competition_scope(database_engine)
    request = _insert_request(
        database_engine, first_scope, scope_key=f"matchups:{uuid4()}"
    )

    _assert_database_error(
        database_engine,
        sa.insert(Matchup).values(
            id=uuid4(),
            competition_season_id=first_scope["season"],
            week=1,
            season_roster_id=second_scope["roster"],
            sleeper_matchup_id=1,
            points=Decimal("123.4567"),
            source_api_request_id=request["request"],
        ),
    )


def test_sealed_snapshot_and_membership_are_immutable_and_scope_safe(
    database_engine: Engine,
) -> None:
    first_scope = _insert_competition_scope(database_engine)
    second_scope = _insert_competition_scope(database_engine)
    first_request = _insert_request(
        database_engine, first_scope, scope_key=f"league:{uuid4()}"
    )
    second_request = _insert_request(
        database_engine, second_scope, scope_key=f"league:{uuid4()}"
    )
    snapshot_id = uuid4()
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(DataSnapshot),
            {
                "id": snapshot_id,
                "competition_id": first_scope["competition"],
                "primary_competition_season_id": first_scope["season"],
                "mode": "test",
                "knowledge_cutoff_at": datetime.now(timezone.utc),
                "status": "building",
                "materializer_version": "test",
                "sqlite_schema_version": "test",
                "code_version": "test",
                "completeness_warnings": [],
            },
        )
        connection.execute(
            sa.insert(DataSnapshotRequest),
            {
                "data_snapshot_id": snapshot_id,
                "api_request_id": first_request["request"],
                "scope_key": first_request["scope_key"],
                "selection_role": "test",
            },
        )

    _assert_database_error(
        database_engine,
        sa.insert(DataSnapshotRequest).values(
            data_snapshot_id=snapshot_id,
            api_request_id=second_request["request"],
            scope_key=second_request["scope_key"],
            selection_role="test",
        ),
    )

    with database_engine.begin() as connection:
        connection.execute(
            sa.update(DataSnapshot)
            .where(DataSnapshot.id == snapshot_id)
            .values(status="ready")
        )

    _assert_database_error(
        database_engine,
        sa.delete(DataSnapshotRequest).where(
            DataSnapshotRequest.data_snapshot_id == snapshot_id
        ),
    )
    _assert_database_error(
        database_engine,
        sa.update(DataSnapshot)
        .where(DataSnapshot.id == snapshot_id)
        .values(materializer_version="rewritten"),
    )
    _assert_database_error(
        database_engine,
        sa.delete(DataSnapshot).where(DataSnapshot.id == snapshot_id),
    )
