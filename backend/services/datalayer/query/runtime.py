"""Context-managed query runtime for one immutable data snapshot."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Self
from uuid import UUID

from backend.services.datalayer.canonical_json import canonical_json_bytes, parse_json_bytes
from backend.services.datalayer.contracts import ReadyDataSnapshot
from backend.services.datalayer.query.curated import (
    get_bench_analysis,
    get_league_snapshot,
    get_player_summary,
    get_player_weekly_log,
    get_playoff_bracket,
    get_roster_at_cutoff,
    get_roster_snapshot,
    get_season_leaders,
    get_standings,
    get_team_dossier,
    get_team_game,
    get_team_game_with_players,
    get_team_playoff_path,
    get_team_schedule,
    get_team_transactions,
    get_transactions,
    get_week_games,
    get_week_games_with_players,
    get_week_player_leaderboard,
)
from backend.services.datalayer.query.guarded_sql import run_guarded_sql
from backend.services.datalayer.snapshot_sqlite.schema import (
    SQLITE_APPLICATION_ID,
    SQLITE_USER_VERSION,
    get_snapshot_schema,
)
from backend.services.datalayer.versions import SNAPSHOT_PROJECTION_VERSION


_CONSTRUCTION_TOKEN = object()
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class FrozenSnapshotInvalid(RuntimeError):
    """A purported ready artifact does not match its sealed snapshot identity."""


class FrozenLeagueData:
    """Read-only curated access to one verified frozen SQLite artifact."""

    def __init__(self, token: object) -> None:
        if token is not _CONSTRUCTION_TOKEN:
            raise TypeError("Use FrozenLeagueData.open(ready_snapshot)")
        self._connection: sqlite3.Connection | None = None
        self._league_id = ""
        self._season = ""
        self._through_week = 0
        self._allowed_tables: frozenset[str] = frozenset()

    @classmethod
    def open(cls, ready_snapshot: ReadyDataSnapshot) -> Self:
        if not isinstance(ready_snapshot, ReadyDataSnapshot):
            raise TypeError("ready_snapshot must be a ReadyDataSnapshot")
        if ready_snapshot.snapshot_projection_version != SNAPSHOT_PROJECTION_VERSION:
            raise FrozenSnapshotInvalid("snapshot projection version is unsupported")
        schema = get_snapshot_schema(ready_snapshot.snapshot_projection_version)
        connection = _open_immutable(ready_snapshot.artifact.path)
        instance = cls(_CONSTRUCTION_TOKEN)
        try:
            metadata = _validate_artifact(connection, ready_snapshot, schema.tables)
            instance._connection = connection
            instance._league_id = metadata["sleeper_league_id"]
            instance._season = str(metadata["season_year"])
            instance._through_week = int(metadata["through_week"])
            instance._allowed_tables = frozenset(schema.tables)
            return instance
        except Exception:
            connection.close()
            raise

    def __enter__(self) -> Self:
        self._conn()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback
        connection, self._connection = self._connection, None
        if connection is not None:
            connection.close()

    def _conn(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("FrozenLeagueData is closed")
        return self._connection

    def _week(self, week: int | None) -> int:
        resolved = self._through_week if week is None else week
        if isinstance(resolved, bool) or not isinstance(resolved, int):
            raise ValueError("week must be an integer")
        if not 1 <= resolved <= self._through_week:
            raise ValueError(f"week must be from 1 through {self._through_week}")
        return resolved

    def _range(self, week_from: int, week_to: int) -> tuple[int, int]:
        start = self._week(week_from)
        end = self._week(week_to)
        if start > end:
            raise ValueError("week_from cannot be greater than week_to")
        return start, end

    def get_league_snapshot(self, week: int | None = None) -> dict[str, Any]:
        return get_league_snapshot(
            self._conn(), self._league_id, self._season, self._week(week)
        )

    def get_bench_analysis(
        self, roster_key: Any = None, week: int | None = None
    ) -> dict[str, Any] | list[dict[str, Any]]:
        return get_bench_analysis(
            self._conn(),
            self._league_id,
            self._season,
            self._week(week),
            roster_key,
        )

    def get_standings(self, week: int | None = None) -> dict[str, Any]:
        return get_standings(
            self._conn(), self._league_id, self._season, self._week(week)
        )

    def get_team_dossier(
        self, roster_key: Any, week: int | None = None
    ) -> dict[str, Any]:
        return get_team_dossier(
            self._conn(),
            self._league_id,
            self._season,
            roster_key,
            self._week(week),
        )

    def get_team_schedule(self, roster_key: Any) -> dict[str, Any]:
        return get_team_schedule(
            self._conn(), self._league_id, self._season, roster_key
        )

    def get_week_games(self, week: int | None = None) -> list[dict[str, Any]]:
        return get_week_games(
            self._conn(), self._league_id, self._season, self._week(week)
        )

    def get_week_games_with_players(
        self, week: int | None = None
    ) -> list[dict[str, Any]]:
        return get_week_games_with_players(
            self._conn(), self._league_id, self._season, self._week(week)
        )

    def get_team_game(
        self, roster_key: Any, week: int | None = None
    ) -> dict[str, Any]:
        return get_team_game(
            self._conn(),
            self._league_id,
            self._season,
            self._week(week),
            roster_key,
        )

    def get_team_game_with_players(
        self, roster_key: Any, week: int | None = None
    ) -> dict[str, Any]:
        return get_team_game_with_players(
            self._conn(),
            self._league_id,
            self._season,
            self._week(week),
            roster_key,
        )

    def get_week_player_leaderboard(
        self, week: int | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        return get_week_player_leaderboard(
            self._conn(),
            self._league_id,
            self._season,
            self._week(week),
            limit=limit,
        )

    def get_season_leaders(
        self,
        *,
        week_from: int | None = None,
        week_to: int | None = None,
        position: str | None = None,
        roster_key: Any = None,
        role: str | None = None,
        sort_by: str = "total",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        if week_from is not None:
            self._week(week_from)
        if week_to is not None:
            self._week(week_to)
        if week_from is not None and week_to is not None and week_from > week_to:
            raise ValueError("week_from cannot be greater than week_to")
        return get_season_leaders(
            self._conn(),
            self._league_id,
            self._season,
            week_from=week_from,
            week_to=week_to,
            position=position,
            roster_key=roster_key,
            role=role,
            sort_by=sort_by,
            limit=limit,
        )

    def get_transactions(self, week_from: int, week_to: int) -> list[dict[str, Any]]:
        start, end = self._range(week_from, week_to)
        return get_transactions(
            self._conn(), self._league_id, self._season, start, end
        )

    def get_team_transactions(
        self, roster_key: Any, week_from: int, week_to: int
    ) -> dict[str, Any]:
        start, end = self._range(week_from, week_to)
        return get_team_transactions(
            self._conn(), self._league_id, self._season, start, end, roster_key
        )

    def get_week_transactions(self, week: int | None = None) -> list[dict[str, Any]]:
        resolved = self._week(week)
        return get_transactions(
            self._conn(), self._league_id, self._season, resolved, resolved
        )

    def get_team_week_transactions(
        self,
        roster_key: Any,
        week_from: int | None = None,
        week_to: int | None = None,
    ) -> dict[str, Any]:
        start = self._week(week_from)
        end = self._week(week_to if week_to is not None else start)
        if start > end:
            raise ValueError("week_from cannot be greater than week_to")
        return get_team_transactions(
            self._conn(), self._league_id, self._season, start, end, roster_key
        )

    def get_player_summary(self, player_key: Any) -> dict[str, Any]:
        return get_player_summary(self._conn(), player_key)

    def get_player_weekly_log(
        self,
        player_key: Any,
        week_from: int | None = None,
        week_to: int | None = None,
    ) -> dict[str, Any]:
        if week_from is not None:
            self._week(week_from)
        if week_to is not None:
            self._week(week_to)
        if week_from is not None and week_to is not None and week_from > week_to:
            raise ValueError("week_from cannot be greater than week_to")
        return get_player_weekly_log(
            self._conn(),
            self._league_id,
            self._season,
            player_key,
            week_from=week_from,
            week_to=week_to,
        )

    def get_roster_at_cutoff(self, roster_key: Any) -> dict[str, Any]:
        return get_roster_at_cutoff(self._conn(), self._league_id, roster_key)

    def get_roster_snapshot(self, roster_key: Any, week: int) -> dict[str, Any]:
        return get_roster_snapshot(
            self._conn(),
            self._league_id,
            self._season,
            roster_key,
            self._week(week),
        )

    def get_playoff_bracket(self, bracket_type: str | None = None) -> dict[str, Any]:
        return get_playoff_bracket(
            self._conn(), self._league_id, self._season, bracket_type
        )

    def get_team_playoff_path(self, roster_key: Any) -> dict[str, Any]:
        return get_team_playoff_path(
            self._conn(), self._league_id, self._season, roster_key
        )

    def run_sql(
        self,
        query: str,
        params: Mapping[str, Any] | None = None,
        *,
        limit: int = 200,
    ) -> dict[str, Any]:
        return run_guarded_sql(
            self._conn(),
            query,
            params,
            limit=limit,
            allowed_tables=self._allowed_tables,
        )


def _open_immutable(path: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(
            f"{path.as_uri()}?mode=ro&immutable=1",
            uri=True,
            check_same_thread=False,
        )
    except (OSError, sqlite3.Error, ValueError) as error:
        raise FrozenSnapshotInvalid("snapshot SQLite artifact is unavailable") from error
    connection.row_factory = sqlite3.Row
    return connection


def _validate_artifact(
    connection: sqlite3.Connection,
    snapshot: ReadyDataSnapshot,
    expected_tables: Mapping[str, Any],
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
    if application_id != SQLITE_APPLICATION_ID or user_version != SQLITE_USER_VERSION:
        raise FrozenSnapshotInvalid("snapshot SQLite version markers differ")
    if table_names != set(expected_tables):
        raise FrozenSnapshotInvalid("snapshot SQLite table set differs")
    if len(rows) != 1:
        raise FrozenSnapshotInvalid("snapshot metadata singleton is invalid")
    metadata = dict(rows[0])
    expected = {
        "competition_id": str(snapshot.competition_id),
        "primary_competition_season_id": str(snapshot.primary_competition_season_id),
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
    warning_json = _validate_canonical_json(
        metadata.get("completeness_warnings_json"), expected_list=True
    )
    expected_warnings = [
        warning.model_dump(mode="json") for warning in snapshot.completeness_warnings
    ]
    if warning_json != expected_warnings:
        raise FrozenSnapshotInvalid("snapshot completeness warnings differ")
    if not isinstance(metadata.get("sleeper_league_id"), str):
        raise FrozenSnapshotInvalid("snapshot league identity is invalid")
    if not isinstance(metadata.get("season_year"), int):
        raise FrozenSnapshotInvalid("snapshot season identity is invalid")
    league = connection.execute(
        """
        SELECT league_id, season FROM leagues
        WHERE league_id = :league_id AND season = :season
        """,
        {
            "league_id": metadata["sleeper_league_id"],
            "season": str(metadata["season_year"]),
        },
    ).fetchall()
    context = connection.execute(
        """
        SELECT effective_week FROM season_context
        WHERE league_id = :league_id
        """,
        {"league_id": metadata["sleeper_league_id"]},
    ).fetchall()
    if len(league) != 1 or len(context) != 1:
        raise FrozenSnapshotInvalid("snapshot league metadata is inconsistent")
    if context[0]["effective_week"] != metadata["through_week"]:
        raise FrozenSnapshotInvalid("snapshot cutoff metadata is inconsistent")
    return metadata


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
