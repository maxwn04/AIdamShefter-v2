"""Context-managed query facade for one immutable data snapshot."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import sqlite3
from typing import Any, Self
from uuid import UUID

from backend.services.datalayer.contracts import ReadyDataSnapshot
from backend.services.datalayer.query.contracts import SnapshotSeason
from backend.services.datalayer.query.curated import (
    get_bench_analysis,
    get_franchise_history,
    get_league_history,
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
    get_week_games,
    get_week_games_with_players,
    get_week_player_leaderboard,
)
from backend.services.datalayer.query.errors import FrozenSnapshotInvalid
from backend.services.datalayer.query.guarded_sql import run_guarded_sql
from backend.services.datalayer.query.identity import (
    FrozenRosterIdentity,
    RosterIdentityResolution,
    get_roster_identity_by_canonical_id,
    resolve_roster_identity,
)
from backend.services.datalayer.query.readers import (
    FrozenSnapshotReader,
    SnapshotSeasonScope,
    open_snapshot_reader,
)
from backend.services.datalayer.snapshot_sqlite.schema import get_snapshot_schema


_CONSTRUCTION_TOKEN = object()


class FrozenLeagueData:
    """Read-only curated access to one verified frozen SQLite artifact."""

    def __init__(self, token: object) -> None:
        if token is not _CONSTRUCTION_TOKEN:
            raise TypeError("Use FrozenLeagueData.open(ready_snapshot)")
        self._connection: sqlite3.Connection | None = None
        self._reader: FrozenSnapshotReader | None = None

    @classmethod
    def open(cls, ready_snapshot: ReadyDataSnapshot) -> Self:
        if not isinstance(ready_snapshot, ReadyDataSnapshot):
            raise TypeError("ready_snapshot must be a ReadyDataSnapshot")
        try:
            schema = get_snapshot_schema(ready_snapshot.snapshot_projection_version)
        except ValueError as error:
            raise FrozenSnapshotInvalid(
                "snapshot projection version is unsupported"
            ) from error
        connection = _open_immutable(ready_snapshot.artifact.path)
        instance = cls(_CONSTRUCTION_TOKEN)
        try:
            instance._reader = open_snapshot_reader(
                connection,
                ready_snapshot,
                schema,
            )
            instance._connection = connection
            return instance
        except Exception:
            connection.close()
            raise

    def __enter__(self) -> Self:
        self._state()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback
        connection, self._connection = self._connection, None
        self._reader = None
        if connection is not None:
            connection.close()

    def _state(self) -> tuple[sqlite3.Connection, FrozenSnapshotReader]:
        if self._connection is None or self._reader is None:
            raise RuntimeError("FrozenLeagueData is closed")
        return self._connection, self._reader

    def _scope(self, season: int | None) -> SnapshotSeasonScope:
        return self._state()[1].scope(season)

    def _week(self, scope: SnapshotSeasonScope, week: int | None) -> int:
        return self._state()[1].week(scope, week)

    def available_seasons(self) -> tuple[SnapshotSeason, ...]:
        return self._state()[1].seasons

    def get_league_history(self) -> dict[str, Any]:
        connection, reader = self._state()
        return get_league_history(connection, reader.seasons)

    def get_franchise_history(
        self,
        franchise_or_primary_roster: str | int,
    ) -> dict[str, Any]:
        connection, reader = self._state()
        return get_franchise_history(
            connection,
            reader.seasons,
            franchise_or_primary_roster,
        )

    def get_league_snapshot(
        self,
        week: int | None = None,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        connection, _ = self._state()
        scope = self._scope(season)
        return get_league_snapshot(
            connection,
            scope.league_id,
            scope.season_year,
            self._week(scope, week),
        )

    def get_bench_analysis(
        self,
        roster_key: Any = None,
        week: int | None = None,
        *,
        season: int | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        connection, _ = self._state()
        scope = self._scope(season)
        return get_bench_analysis(
            connection,
            scope.league_id,
            scope.season_year,
            self._week(scope, week),
            roster_key,
        )

    def get_standings(
        self,
        week: int | None = None,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        connection, _ = self._state()
        scope = self._scope(season)
        return get_standings(
            connection,
            scope.league_id,
            scope.season_year,
            self._week(scope, week),
        )

    def get_team_dossier(
        self,
        roster_key: Any,
        week: int | None = None,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        connection, _ = self._state()
        scope = self._scope(season)
        return get_team_dossier(
            connection,
            scope.league_id,
            scope.season_year,
            roster_key,
            self._week(scope, week),
        )

    def get_team_schedule(
        self,
        roster_key: Any,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        connection, _ = self._state()
        scope = self._scope(season)
        return get_team_schedule(
            connection,
            scope.league_id,
            scope.season_year,
            roster_key,
        )

    def get_week_games(
        self,
        week: int | None = None,
        *,
        season: int | None = None,
    ) -> list[dict[str, Any]]:
        connection, _ = self._state()
        scope = self._scope(season)
        return get_week_games(
            connection,
            scope.league_id,
            scope.season_year,
            self._week(scope, week),
        )

    def get_week_games_with_players(
        self,
        week: int | None = None,
        *,
        season: int | None = None,
    ) -> list[dict[str, Any]]:
        connection, _ = self._state()
        scope = self._scope(season)
        return get_week_games_with_players(
            connection,
            scope.league_id,
            scope.season_year,
            self._week(scope, week),
        )

    def get_team_game(
        self,
        roster_key: Any,
        week: int | None = None,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        connection, _ = self._state()
        scope = self._scope(season)
        return get_team_game(
            connection,
            scope.league_id,
            scope.season_year,
            self._week(scope, week),
            roster_key,
        )

    def get_team_game_with_players(
        self,
        roster_key: Any,
        week: int | None = None,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        connection, _ = self._state()
        scope = self._scope(season)
        return get_team_game_with_players(
            connection,
            scope.league_id,
            scope.season_year,
            self._week(scope, week),
            roster_key,
        )

    def get_week_player_leaderboard(
        self,
        week: int | None = None,
        limit: int = 10,
        *,
        season: int | None = None,
    ) -> list[dict[str, Any]]:
        connection, _ = self._state()
        scope = self._scope(season)
        return get_week_player_leaderboard(
            connection,
            scope.league_id,
            scope.season_year,
            self._week(scope, week),
            limit=limit,
        )

    def get_season_leaders(
        self,
        *,
        season: int | None = None,
        week_from: int | None = None,
        week_to: int | None = None,
        position: str | None = None,
        roster_key: Any = None,
        role: str | None = None,
        sort_by: str = "total",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        connection, _ = self._state()
        scope = self._scope(season)
        if week_from is not None:
            self._week(scope, week_from)
        if week_to is not None:
            self._week(scope, week_to)
        if week_from is not None and week_to is not None and week_from > week_to:
            raise ValueError("week_from cannot be greater than week_to")
        return get_season_leaders(
            connection,
            scope.league_id,
            scope.season_year,
            week_from=week_from,
            week_to=week_to,
            position=position,
            roster_key=roster_key,
            role=role,
            sort_by=sort_by,
            limit=limit,
        )

    def get_transactions(
        self,
        week_from: int,
        week_to: int,
        *,
        season: int | None = None,
    ) -> list[dict[str, Any]]:
        _, reader = self._state()
        scope = reader.scope(season)
        start, end = reader.week_range(scope, week_from, week_to)
        return reader.get_transactions(scope, start, end)

    def get_team_transactions(
        self,
        roster_key: Any,
        week_from: int,
        week_to: int,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        _, reader = self._state()
        scope = reader.scope(season)
        start, end = reader.week_range(scope, week_from, week_to)
        return reader.get_team_transactions(scope, start, end, roster_key)

    def get_week_transactions(
        self,
        week: int | None = None,
        *,
        season: int | None = None,
    ) -> list[dict[str, Any]]:
        _, reader = self._state()
        scope = reader.scope(season)
        resolved = reader.week(scope, week)
        return reader.get_transactions(scope, resolved, resolved)

    def get_team_week_transactions(
        self,
        roster_key: Any,
        week_from: int | None = None,
        week_to: int | None = None,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        _, reader = self._state()
        scope = reader.scope(season)
        start = reader.week(scope, week_from)
        end = reader.week(scope, week_to if week_to is not None else start)
        if start > end:
            raise ValueError("week_from cannot be greater than week_to")
        return reader.get_team_transactions(scope, start, end, roster_key)

    def get_player_summary(self, player_key: Any) -> dict[str, Any]:
        return get_player_summary(self._state()[0], player_key)

    def get_player_weekly_log(
        self,
        player_key: Any,
        week_from: int | None = None,
        week_to: int | None = None,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        connection, _ = self._state()
        scope = self._scope(season)
        if week_from is not None:
            self._week(scope, week_from)
        if week_to is not None:
            self._week(scope, week_to)
        if week_from is not None and week_to is not None and week_from > week_to:
            raise ValueError("week_from cannot be greater than week_to")
        return get_player_weekly_log(
            connection,
            scope.league_id,
            scope.season_year,
            player_key,
            week_from=week_from,
            week_to=week_to,
        )

    def get_roster_at_cutoff(
        self,
        roster_key: Any,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        connection, _ = self._state()
        scope = self._scope(season)
        return get_roster_at_cutoff(connection, scope.league_id, roster_key)

    def resolve_roster_identity(
        self,
        roster_key: str | int,
        *,
        season: int | None = None,
    ) -> RosterIdentityResolution:
        connection, _ = self._state()
        selected = self._scope(season).season
        return resolve_roster_identity(
            connection,
            competition_id=selected.competition_id,
            competition_season_id=selected.competition_season_id,
            league_id=selected.sleeper_league_id,
            roster_key=roster_key,
        )

    def get_roster_identity_by_canonical_id(
        self,
        *,
        franchise_id: UUID | None = None,
        season_roster_id: UUID | None = None,
        season: int | None = None,
    ) -> FrozenRosterIdentity | None:
        connection, _ = self._state()
        selected = self._scope(season).season
        return get_roster_identity_by_canonical_id(
            connection,
            competition_id=selected.competition_id,
            competition_season_id=selected.competition_season_id,
            league_id=selected.sleeper_league_id,
            franchise_id=franchise_id,
            season_roster_id=season_roster_id,
        )

    def get_roster_snapshot(
        self,
        roster_key: Any,
        week: int,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        connection, _ = self._state()
        scope = self._scope(season)
        return get_roster_snapshot(
            connection,
            scope.league_id,
            scope.season_year,
            roster_key,
            self._week(scope, week),
        )

    def get_playoff_bracket(
        self,
        bracket_type: str | None = None,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        connection, _ = self._state()
        scope = self._scope(season)
        return get_playoff_bracket(
            connection,
            scope.league_id,
            scope.season_year,
            bracket_type,
        )

    def get_team_playoff_path(
        self,
        roster_key: Any,
        *,
        season: int | None = None,
    ) -> dict[str, Any]:
        connection, _ = self._state()
        scope = self._scope(season)
        return get_team_playoff_path(
            connection,
            scope.league_id,
            scope.season_year,
            roster_key,
        )

    def run_sql(
        self,
        query: str,
        params: Mapping[str, Any] | None = None,
        *,
        limit: int = 200,
    ) -> dict[str, Any]:
        connection, reader = self._state()
        return run_guarded_sql(
            connection,
            query,
            params,
            limit=limit,
            allowed_tables=reader.allowed_tables,
        )


def _open_immutable(path: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(
            f"{path.as_uri()}?mode=ro&immutable=1",
            uri=True,
            check_same_thread=False,
        )
    except (OSError, sqlite3.Error, ValueError) as error:
        raise FrozenSnapshotInvalid(
            "snapshot SQLite artifact is unavailable"
        ) from error
    connection.row_factory = sqlite3.Row
    return connection


__all__ = ["FrozenLeagueData", "FrozenSnapshotInvalid"]
