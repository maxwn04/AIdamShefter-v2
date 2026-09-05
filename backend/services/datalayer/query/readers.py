"""Version-specific readers for validated immutable snapshot artifacts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import re
import sqlite3
from typing import Any
from uuid import UUID

from backend.services.datalayer.canonical_json import (
    canonical_json_bytes,
    parse_json_bytes,
)
from backend.services.datalayer.contracts import ReadyDataSnapshot
from backend.services.datalayer.query.contracts import SnapshotSeason
from backend.services.datalayer.query.curated.transactions import (
    get_team_transactions as get_team_transactions_v2,
)
from backend.services.datalayer.query.curated.transactions import (
    get_transactions as get_transactions_v2,
)
from backend.services.datalayer.query.curated.transactions_v3 import (
    get_team_transactions as get_team_transactions_v3,
)
from backend.services.datalayer.query.curated.transactions_v3 import (
    get_transactions as get_transactions_v3,
)
from backend.services.datalayer.query.errors import FrozenSnapshotInvalid
from backend.services.datalayer.snapshot_sqlite.schema import (
    SQLITE_APPLICATION_ID,
    SnapshotSchema,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
TransactionQuery = Callable[
    [sqlite3.Connection, str, str, int, int],
    list[dict[str, Any]],
]
TeamTransactionQuery = Callable[
    [sqlite3.Connection, str, str, int, int, Any],
    dict[str, Any],
]


@dataclass(frozen=True, slots=True)
class SnapshotSeasonScope:
    season: SnapshotSeason

    @property
    def league_id(self) -> str:
        return self.season.sleeper_league_id

    @property
    def season_year(self) -> str:
        return str(self.season.season_year)

    @property
    def through_week(self) -> int:
        return self.season.through_week


class FrozenSnapshotReader:
    """Validated version-specific state used by the public runtime facade."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        schema: SnapshotSchema,
        seasons: tuple[SnapshotSeason, ...],
        *,
        transaction_query: TransactionQuery,
        team_transaction_query: TeamTransactionQuery,
    ) -> None:
        self.connection = connection
        self.allowed_tables = frozenset(schema.tables)
        self.seasons = seasons
        self._seasons_by_year = {season.season_year: season for season in seasons}
        self.primary = next(season for season in seasons if season.role == "primary")
        self._transaction_query = transaction_query
        self._team_transaction_query = team_transaction_query

    def scope(self, season: int | None) -> SnapshotSeasonScope:
        if season is None:
            return SnapshotSeasonScope(self.primary)
        if isinstance(season, bool) or not isinstance(season, int):
            raise ValueError("season must be an integer")
        selected = self._seasons_by_year.get(season)
        if selected is None:
            available = ", ".join(str(item.season_year) for item in self.seasons)
            raise ValueError(f"season must be one of: {available}")
        return SnapshotSeasonScope(selected)

    @staticmethod
    def week(scope: SnapshotSeasonScope, week: int | None) -> int:
        resolved = scope.through_week if week is None else week
        if isinstance(resolved, bool) or not isinstance(resolved, int):
            raise ValueError("week must be an integer")
        if not 1 <= resolved <= scope.through_week:
            raise ValueError(f"week must be from 1 through {scope.through_week}")
        return resolved

    def week_range(
        self,
        scope: SnapshotSeasonScope,
        week_from: int,
        week_to: int,
    ) -> tuple[int, int]:
        start = self.week(scope, week_from)
        end = self.week(scope, week_to)
        if start > end:
            raise ValueError("week_from cannot be greater than week_to")
        return start, end

    def get_transactions(
        self,
        scope: SnapshotSeasonScope,
        week_from: int,
        week_to: int,
    ) -> list[dict[str, Any]]:
        return self._transaction_query(
            self.connection,
            scope.league_id,
            scope.season_year,
            week_from,
            week_to,
        )

    def get_team_transactions(
        self,
        scope: SnapshotSeasonScope,
        week_from: int,
        week_to: int,
        roster_key: Any,
    ) -> dict[str, Any]:
        return self._team_transaction_query(
            self.connection,
            scope.league_id,
            scope.season_year,
            week_from,
            week_to,
            roster_key,
        )


class _V2SnapshotReader(FrozenSnapshotReader):
    def __init__(
        self,
        connection: sqlite3.Connection,
        snapshot: ReadyDataSnapshot,
        schema: SnapshotSchema,
        metadata: dict[str, Any],
    ) -> None:
        sequence_number = 1
        if len(snapshot.included_seasons) == 1:
            membership = snapshot.included_seasons[0]
            expected = (
                snapshot.primary_competition_season_id,
                metadata["sleeper_league_id"],
                metadata["season_year"],
                "primary",
                metadata["through_week"],
            )
            actual = (
                membership.competition_season_id,
                membership.sleeper_league_id,
                membership.season_year,
                membership.role,
                membership.through_week,
            )
            if actual != expected:
                raise FrozenSnapshotInvalid(
                    "snapshot season membership differs from ready identity"
                )
            sequence_number = membership.sequence_number
        elif snapshot.included_seasons:
            raise FrozenSnapshotInvalid(
                "version-2 snapshot has multiple season memberships"
            )
        season = SnapshotSeason(
            competition_id=snapshot.competition_id,
            competition_season_id=snapshot.primary_competition_season_id,
            sleeper_league_id=metadata["sleeper_league_id"],
            season_year=metadata["season_year"],
            sequence_number=sequence_number,
            role="primary",
            through_week=metadata["through_week"],
        )
        _validate_season_data(connection, (season,))
        _validate_roster_identities(connection, (season,), version="2")
        super().__init__(
            connection,
            schema,
            (season,),
            transaction_query=get_transactions_v2,
            team_transaction_query=get_team_transactions_v2,
        )


class _V3SnapshotReader(FrozenSnapshotReader):
    def __init__(
        self,
        connection: sqlite3.Connection,
        snapshot: ReadyDataSnapshot,
        schema: SnapshotSchema,
        metadata: dict[str, Any],
    ) -> None:
        if snapshot.input_revision is None or metadata.get("input_revision") != (
            snapshot.input_revision
        ):
            raise FrozenSnapshotInvalid("snapshot input revision differs")
        seasons = _read_v3_seasons(connection)
        _validate_v3_catalog(seasons, snapshot, metadata)
        _validate_season_data(connection, seasons)
        _validate_roster_identities(connection, seasons, version="3")
        super().__init__(
            connection,
            schema,
            seasons,
            transaction_query=get_transactions_v3,
            team_transaction_query=get_team_transactions_v3,
        )


def open_snapshot_reader(
    connection: sqlite3.Connection,
    snapshot: ReadyDataSnapshot,
    schema: SnapshotSchema,
) -> FrozenSnapshotReader:
    metadata = _validate_common_artifact(connection, snapshot, schema)
    if schema.projection_version == "2":
        return _V2SnapshotReader(connection, snapshot, schema, metadata)
    if schema.projection_version == "3":
        return _V3SnapshotReader(connection, snapshot, schema, metadata)
    raise FrozenSnapshotInvalid("snapshot projection version is unsupported")


def _validate_common_artifact(
    connection: sqlite3.Connection,
    snapshot: ReadyDataSnapshot,
    schema: SnapshotSchema,
) -> dict[str, Any]:
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        application_id = connection.execute("PRAGMA application_id").fetchone()[0]
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            )
        }
        rows = connection.execute("SELECT * FROM snapshot_metadata").fetchall()
    except sqlite3.Error as error:
        raise FrozenSnapshotInvalid("snapshot SQLite metadata is unreadable") from error
    if integrity is None or integrity[0] != "ok":
        raise FrozenSnapshotInvalid("snapshot SQLite integrity check failed")
    if application_id != SQLITE_APPLICATION_ID or user_version != schema.user_version:
        raise FrozenSnapshotInvalid("snapshot SQLite version markers differ")
    if table_names != set(schema.tables):
        raise FrozenSnapshotInvalid("snapshot SQLite table set differs")
    if len(rows) != 1:
        raise FrozenSnapshotInvalid("snapshot metadata singleton is invalid")

    metadata = dict(rows[0])
    expected = {
        "competition_id": str(snapshot.competition_id),
        "primary_competition_season_id": str(
            snapshot.primary_competition_season_id
        ),
        "through_week": snapshot.through_week,
        "as_of_date": snapshot.as_of_date.isoformat(),
        "build_key": snapshot.build_key,
        "snapshot_projection_version": snapshot.snapshot_projection_version,
    }
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise FrozenSnapshotInvalid("snapshot metadata differs from ready identity")
    selected_requests = _validate_canonical_json(
        metadata.get("selected_requests_json"), expected_list=True
    )
    _validate_manifest_entries(selected_requests)
    warnings = _validate_canonical_json(
        metadata.get("completeness_warnings_json"), expected_list=True
    )
    expected_warnings = [
        warning.model_dump(mode="json") for warning in snapshot.completeness_warnings
    ]
    if warnings != expected_warnings:
        raise FrozenSnapshotInvalid("snapshot completeness warnings differ")
    if not isinstance(metadata.get("sleeper_league_id"), str) or not metadata[
        "sleeper_league_id"
    ]:
        raise FrozenSnapshotInvalid("snapshot league identity is invalid")
    if not isinstance(metadata.get("season_year"), int):
        raise FrozenSnapshotInvalid("snapshot season identity is invalid")
    return metadata


def _read_v3_seasons(
    connection: sqlite3.Connection,
) -> tuple[SnapshotSeason, ...]:
    try:
        rows = connection.execute(
            "SELECT competition_id, competition_season_id, league_id, "
            "season_year, sequence_number, role, through_week "
            "FROM snapshot_seasons ORDER BY sequence_number"
        ).fetchall()
        return tuple(
            SnapshotSeason(
                competition_id=row["competition_id"],
                competition_season_id=row["competition_season_id"],
                sleeper_league_id=row["league_id"],
                season_year=row["season_year"],
                sequence_number=row["sequence_number"],
                role=row["role"],
                through_week=row["through_week"],
            )
            for row in rows
        )
    except (sqlite3.Error, TypeError, ValueError) as error:
        raise FrozenSnapshotInvalid("snapshot season catalog is invalid") from error


def _validate_v3_catalog(
    seasons: tuple[SnapshotSeason, ...],
    snapshot: ReadyDataSnapshot,
    metadata: dict[str, Any],
) -> None:
    if not seasons or not snapshot.included_seasons:
        raise FrozenSnapshotInvalid("snapshot season catalog is empty")
    if tuple(sorted(seasons, key=lambda item: item.sequence_number)) != seasons:
        raise FrozenSnapshotInvalid("snapshot season catalog order is invalid")
    primary = tuple(season for season in seasons if season.role == "primary")
    if len(primary) != 1 or primary[0] != seasons[-1]:
        raise FrozenSnapshotInvalid("snapshot primary season catalog is invalid")
    if any(season.through_week != 18 for season in seasons[:-1]):
        raise FrozenSnapshotInvalid("snapshot historical cutoff is invalid")
    if any(season.competition_id != snapshot.competition_id for season in seasons):
        raise FrozenSnapshotInvalid("snapshot season competition differs")
    primary_season = primary[0]
    expected_primary = (
        snapshot.primary_competition_season_id,
        metadata["sleeper_league_id"],
        metadata["season_year"],
        metadata["through_week"],
    )
    if (
        primary_season.competition_season_id,
        primary_season.sleeper_league_id,
        primary_season.season_year,
        primary_season.through_week,
    ) != expected_primary:
        raise FrozenSnapshotInvalid("snapshot primary season differs")
    actual = tuple(
        (
            season.competition_season_id,
            season.sleeper_league_id,
            season.season_year,
            season.sequence_number,
            season.role,
            season.through_week,
        )
        for season in seasons
    )
    expected = tuple(
        (
            season.competition_season_id,
            season.sleeper_league_id,
            season.season_year,
            season.sequence_number,
            season.role,
            season.through_week,
        )
        for season in snapshot.included_seasons
    )
    if actual != expected:
        raise FrozenSnapshotInvalid(
            "snapshot season membership differs from ready identity"
        )


def _validate_season_data(
    connection: sqlite3.Connection,
    seasons: tuple[SnapshotSeason, ...],
) -> None:
    for season in seasons:
        try:
            league = connection.execute(
                "SELECT 1 FROM leagues WHERE league_id = :league_id "
                "AND season = :season",
                {
                    "league_id": season.sleeper_league_id,
                    "season": str(season.season_year),
                },
            ).fetchall()
            context = connection.execute(
                "SELECT effective_week FROM season_context "
                "WHERE league_id = :league_id",
                {"league_id": season.sleeper_league_id},
            ).fetchall()
        except sqlite3.Error as error:
            raise FrozenSnapshotInvalid(
                "snapshot league metadata is unreadable"
            ) from error
        if len(league) != 1 or len(context) != 1:
            raise FrozenSnapshotInvalid("snapshot league metadata is inconsistent")
        if context[0]["effective_week"] != season.through_week:
            raise FrozenSnapshotInvalid("snapshot cutoff metadata is inconsistent")


def _validate_roster_identities(
    connection: sqlite3.Connection,
    seasons: tuple[SnapshotSeason, ...],
    *,
    version: str,
) -> None:
    try:
        rosters = {
            (row["league_id"], row["roster_id"])
            for row in connection.execute(
                "SELECT league_id, roster_id FROM rosters"
            ).fetchall()
        }
        identities = connection.execute(
            "SELECT * FROM roster_identities ORDER BY league_id, roster_id"
        ).fetchall()
    except sqlite3.Error as error:
        raise FrozenSnapshotInvalid(
            "snapshot roster identities are unreadable"
        ) from error
    if {(row["league_id"], row["roster_id"]) for row in identities} != rosters:
        raise FrozenSnapshotInvalid(
            "snapshot roster identities do not match snapshot rosters"
        )
    scopes = {season.sleeper_league_id: season for season in seasons}
    for row in identities:
        season = scopes.get(row["league_id"])
        if season is None or (
            row["competition_id"],
            row["competition_season_id"],
        ) != (str(season.competition_id), str(season.competition_season_id)):
            raise FrozenSnapshotInvalid(
                "snapshot roster identities are outside the snapshot scope"
            )
    for field in ("season_roster_id", "franchise_id"):
        values = [row[field] for row in identities]
        try:
            canonical = [str(UUID(value)) for value in values]
        except (AttributeError, TypeError, ValueError) as error:
            raise FrozenSnapshotInvalid(
                f"snapshot roster identity {field} is invalid"
            ) from error
        if values != canonical:
            raise FrozenSnapshotInvalid(
                f"snapshot roster identity {field} is invalid"
            )
        uniqueness_keys = (
            values
            if field == "season_roster_id" or version == "2"
            else [
                (row["competition_season_id"], row[field]) for row in identities
            ]
        )
        if len(uniqueness_keys) != len(set(uniqueness_keys)):
            raise FrozenSnapshotInvalid(
                f"snapshot roster identity {field} is invalid"
            )


def _validate_canonical_json(value: Any, *, expected_list: bool) -> Any:
    if not isinstance(value, str):
        raise FrozenSnapshotInvalid("snapshot manifest metadata is invalid")
    try:
        parsed = parse_json_bytes(value.encode("utf-8"))
        canonical = canonical_json_bytes(parsed).decode("utf-8")
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise FrozenSnapshotInvalid("snapshot manifest metadata is invalid") from error
    if canonical != value or (expected_list and not isinstance(parsed, list)):
        raise FrozenSnapshotInvalid("snapshot manifest metadata is not canonical")
    return parsed


def _validate_manifest_entries(entries: Any) -> None:
    required = {
        "request_id",
        "endpoint_kind",
        "scope_key",
        "selection_role",
        "response_sha256",
    }
    if not isinstance(entries, list) or not entries:
        raise FrozenSnapshotInvalid("snapshot request manifest is empty")
    request_ids: set[str] = set()
    scope_keys: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != required:
            raise FrozenSnapshotInvalid("snapshot request manifest entry is invalid")
        try:
            request_id = str(UUID(entry["request_id"]))
        except (AttributeError, TypeError, ValueError) as error:
            raise FrozenSnapshotInvalid(
                "snapshot request manifest entry is invalid"
            ) from error
        scope_value = entry["scope_key"]
        if isinstance(scope_value, dict) and set(scope_value) == {"value"}:
            scope_value = scope_value["value"]
        strings = (entry["endpoint_kind"], scope_value, entry["selection_role"])
        if any(not isinstance(item, str) or not item for item in strings):
            raise FrozenSnapshotInvalid("snapshot request manifest entry is invalid")
        sha256 = entry["response_sha256"]
        if not isinstance(sha256, str) or _SHA256.fullmatch(sha256) is None:
            raise FrozenSnapshotInvalid("snapshot request manifest entry is invalid")
        if request_id in request_ids or scope_value in scope_keys:
            raise FrozenSnapshotInvalid("snapshot request manifest contains duplicates")
        request_ids.add(request_id)
        scope_keys.add(scope_value)


__all__ = [
    "FrozenSnapshotReader",
    "SnapshotSeasonScope",
    "open_snapshot_reader",
]
