from datetime import date, datetime, timezone
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
    AutomaticRefreshClaim,
    DataSnapshot,
    DataSnapshotRequest,
    DataSnapshotSeason,
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


def _insert_successor_season(
    engine: Engine,
    scope: dict[str, UUID],
) -> dict[str, UUID]:
    successor = {**scope, "season": uuid4()}
    with engine.begin() as connection:
        connection.execute(
            sa.insert(CompetitionSeason),
            {
                "id": successor["season"],
                "competition_id": scope["competition"],
                "season_year": 2027,
                "sequence_number": 2,
                "sleeper_league_id": f"league-{uuid4()}",
            },
        )
    return successor


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
    assert len(sleeper_tables) == 21

    checks = [
        (table_name, constraint.name)
        for table_name in sleeper_tables
        for constraint in Base.metadata.tables[table_name].constraints
        if isinstance(constraint, CheckConstraint)
    ]
    assert set(checks) == {
        ("sleeper.api_payloads", "ck_api_payloads_exactly_one_location"),
        (
            "sleeper.automatic_refresh_claims",
            "ck_automatic_refresh_claims_reason",
        ),
        (
            "sleeper.automatic_refresh_claims",
            "ck_automatic_refresh_claims_status",
        ),
        (
            "sleeper.automatic_refresh_claims",
            "ck_automatic_refresh_claims_terminal_shape",
        ),
        (
            "sleeper.automatic_refresh_claims",
            "ck_automatic_refresh_claims_through_week",
        ),
        ("sleeper.data_snapshot_seasons", "ck_data_snapshot_seasons_role"),
        (
            "sleeper.data_snapshot_seasons",
            "ck_data_snapshot_seasons_primary_matches",
        ),
        (
            "sleeper.data_snapshot_seasons",
            "ck_data_snapshot_seasons_through_week",
        ),
    }

    for table_name, column_name in (
        ("sleeper.matchups", "points"),
        ("sleeper.player_performances", "points"),
        ("sleeper.rosters", "points_for"),
        ("sleeper.rosters", "points_against"),
    ):
        column_type = Base.metadata.tables[table_name].c[column_name].type
        assert isinstance(column_type, Numeric)
        assert (column_type.precision, column_type.scale) == (12, 4)


def test_snapshot_orm_matches_the_daily_persistence_contract() -> None:
    snapshot = DataSnapshot.__table__
    membership = DataSnapshotRequest.__table__
    season_membership = DataSnapshotSeason.__table__
    refresh_claim = AutomaticRefreshClaim.__table__

    assert {column.name for column in snapshot.c} == {
        "id",
        "competition_id",
        "primary_competition_season_id",
        "build_key",
        "input_revision",
        "domain_cutoff_week",
        "domain_cutoff_at",
        "as_of_date",
        "status",
        "snapshot_projection_version",
        "code_version",
        "completeness_warnings",
        "failure_summary",
        "sqlite_artifact_sha256",
        "sqlite_artifact_byte_length",
        "sqlite_artifact_storage_key",
        "created_at",
        "completed_at",
    }
    assert {column.name for column in membership.c} == {
        "data_snapshot_id",
        "api_request_id",
        "scope_key",
        "response_sha256",
        "selection_role",
    }
    assert {column.name for column in season_membership.c} == {
        "data_snapshot_id",
        "competition_id",
        "primary_competition_season_id",
        "competition_season_id",
        "role",
        "through_week",
    }
    assert {column.name for column in refresh_claim.c} == {
        "id",
        "competition_id",
        "competition_season_id",
        "active_key",
        "requested_through_week",
        "policy_version",
        "reason",
        "coverage_fingerprint",
        "status",
        "refresh_run_id",
        "refresh_status",
        "failure_summary",
        "started_at",
        "completed_at",
    }
    active_build_index = next(
        index
        for index in snapshot.indexes
        if index.name == "uq_data_snapshots_active_build_key"
    )
    assert active_build_index.unique is True
    assert str(active_build_index.dialect_options["postgresql"]["where"]) == (
        "status IN ('building', 'ready')"
    )
    request_fk = next(
        constraint
        for constraint in membership.foreign_key_constraints
        if constraint.name == "fk_data_snapshot_requests_request_scope_hash"
    )
    assert [element.parent.name for element in request_fk.elements] == [
        "api_request_id",
        "scope_key",
        "response_sha256",
    ]


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
                "competition_season_id": scope["season"],
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
            competition_season_id=scope["season"],
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
                "build_key": f"test:{snapshot_id}",
                "domain_cutoff_week": 8,
                "as_of_date": date(2026, 10, 27),
                "status": "building",
                "snapshot_projection_version": "test",
                "code_version": "test",
                "completeness_warnings": [],
            },
        )
        connection.execute(
            sa.insert(DataSnapshotSeason),
            {
                "data_snapshot_id": snapshot_id,
                "competition_id": first_scope["competition"],
                "primary_competition_season_id": first_scope["season"],
                "competition_season_id": first_scope["season"],
                "role": "primary",
                "through_week": 8,
            },
        )
        connection.execute(
            sa.insert(DataSnapshotRequest),
            {
                "data_snapshot_id": snapshot_id,
                "api_request_id": first_request["request"],
                "scope_key": first_request["scope_key"],
                "response_sha256": first_request["hash"],
                "selection_role": "test",
            },
        )

    _assert_database_error(
        database_engine,
        sa.insert(DataSnapshotRequest).values(
            data_snapshot_id=snapshot_id,
            api_request_id=second_request["request"],
            scope_key=second_request["scope_key"],
            response_sha256=second_request["hash"],
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
        .values(snapshot_projection_version="rewritten"),
    )
    _assert_database_error(
        database_engine,
        sa.update(DataSnapshot)
        .where(DataSnapshot.id == snapshot_id)
        .values(input_revision="f" * 64),
    )
    _assert_database_error(
        database_engine,
        sa.delete(DataSnapshotSeason).where(
            DataSnapshotSeason.data_snapshot_id == snapshot_id
        ),
    )
    with database_engine.begin() as connection:
        connection.execute(
            sa.update(DataSnapshot)
            .where(DataSnapshot.id == snapshot_id)
            .values(status="expired")
        )
    _assert_database_error(
        database_engine,
        sa.update(DataSnapshot)
        .where(DataSnapshot.id == snapshot_id)
        .values(status="ready"),
    )
    _assert_database_error(
        database_engine,
        sa.delete(DataSnapshot).where(DataSnapshot.id == snapshot_id),
    )


def test_snapshot_membership_accepts_included_historical_seasons(
    database_engine: Engine,
) -> None:
    historical = _insert_competition_scope(database_engine)
    primary = _insert_successor_season(database_engine, historical)
    historical_request = _insert_request(
        database_engine,
        historical,
        scope_key=f"league:{historical['season']}",
    )
    primary_request = _insert_request(
        database_engine,
        primary,
        scope_key=f"league:{primary['season']}",
    )
    snapshot_id = uuid4()
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(DataSnapshot),
            {
                "id": snapshot_id,
                "competition_id": historical["competition"],
                "primary_competition_season_id": primary["season"],
                "build_key": f"test:{snapshot_id}",
                "input_revision": "a" * 64,
                "domain_cutoff_week": 8,
                "as_of_date": date(2027, 10, 27),
                "status": "building",
                "snapshot_projection_version": "3",
                "code_version": "test",
                "completeness_warnings": [],
            },
        )
        connection.execute(
            sa.insert(DataSnapshotSeason),
            (
                {
                    "data_snapshot_id": snapshot_id,
                    "competition_id": historical["competition"],
                    "primary_competition_season_id": primary["season"],
                    "competition_season_id": historical["season"],
                    "role": "history",
                    "through_week": 18,
                },
                {
                    "data_snapshot_id": snapshot_id,
                    "competition_id": historical["competition"],
                    "primary_competition_season_id": primary["season"],
                    "competition_season_id": primary["season"],
                    "role": "primary",
                    "through_week": 8,
                },
            ),
        )
        connection.execute(
            sa.insert(DataSnapshotRequest),
            (
                {
                    "data_snapshot_id": snapshot_id,
                    "api_request_id": historical_request["request"],
                    "scope_key": historical_request["scope_key"],
                    "response_sha256": historical_request["hash"],
                    "selection_role": "league",
                },
                {
                    "data_snapshot_id": snapshot_id,
                    "api_request_id": primary_request["request"],
                    "scope_key": primary_request["scope_key"],
                    "response_sha256": primary_request["hash"],
                    "selection_role": "league",
                },
            ),
        )
        connection.execute(
            sa.update(DataSnapshot)
            .where(DataSnapshot.id == snapshot_id)
            .values(status="ready")
        )

    with database_engine.connect() as connection:
        assert connection.scalar(
            sa.select(sa.func.count())
            .select_from(DataSnapshotSeason)
            .where(DataSnapshotSeason.data_snapshot_id == snapshot_id)
        ) == 2
        assert connection.scalar(
            sa.select(sa.func.count())
            .select_from(DataSnapshotRequest)
            .where(DataSnapshotRequest.data_snapshot_id == snapshot_id)
        ) == 2


def test_only_active_snapshots_reserve_a_build_key(database_engine: Engine) -> None:
    scope = _insert_competition_scope(database_engine)
    build_key = f"snapshot:{uuid4()}"

    def values(status: str) -> dict[str, object]:
        return {
            "id": uuid4(),
            "competition_id": scope["competition"],
            "primary_competition_season_id": scope["season"],
            "build_key": build_key,
            "domain_cutoff_week": 8,
            "as_of_date": date(2026, 10, 27),
            "status": status,
            "snapshot_projection_version": "test",
            "code_version": "test",
            "completeness_warnings": [],
        }

    active = values("building")
    with database_engine.begin() as connection:
        connection.execute(sa.insert(DataSnapshot), values("failed"))
        connection.execute(sa.insert(DataSnapshot), active)

    _assert_database_error(
        database_engine,
        sa.insert(DataSnapshot).values(**values("ready")),
    )
    with database_engine.begin() as connection:
        connection.execute(
            sa.update(DataSnapshot)
            .where(DataSnapshot.id == active["id"])
            .values(status="failed")
        )
        ready = values("ready")
        connection.execute(sa.insert(DataSnapshot), ready)
        connection.execute(
            sa.update(DataSnapshot)
            .where(DataSnapshot.id == ready["id"])
            .values(status="expired")
        )
        connection.execute(sa.insert(DataSnapshot), values("building"))


def test_snapshot_membership_pins_the_request_response_hash(
    database_engine: Engine,
) -> None:
    scope = _insert_competition_scope(database_engine)
    request = _insert_request(
        database_engine,
        scope,
        scope_key=f"league:{scope['season']}",
    )
    snapshot_id = uuid4()
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(DataSnapshot),
            {
                "id": snapshot_id,
                "competition_id": scope["competition"],
                "primary_competition_season_id": scope["season"],
                "build_key": f"test:{snapshot_id}",
                "domain_cutoff_week": 8,
                "as_of_date": date(2026, 10, 27),
                "status": "building",
                "snapshot_projection_version": "test",
                "code_version": "test",
                "completeness_warnings": [],
            },
        )
        connection.execute(
            sa.insert(DataSnapshotSeason),
            {
                "data_snapshot_id": snapshot_id,
                "competition_id": scope["competition"],
                "primary_competition_season_id": scope["season"],
                "competition_season_id": scope["season"],
                "role": "primary",
                "through_week": 8,
            },
        )

    _assert_database_error(
        database_engine,
        sa.insert(DataSnapshotRequest).values(
            data_snapshot_id=snapshot_id,
            api_request_id=request["request"],
            scope_key=request["scope_key"],
            response_sha256="0" * 64,
            selection_role="league",
        ),
    )
