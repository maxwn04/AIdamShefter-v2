"""A Week 0 snapshot retains rosters/history without current-season results."""

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from backend.services.datalayer import FrozenLeagueData
from backend.services.datalayer.contracts import ReadyDataSnapshot, ReadySnapshotSeason
from backend.services.datalayer.local_files import VerifiedLocalArtifact
from backend.services.datalayer.query.curated.league import get_league_snapshot
from backend.services.datalayer.snapshot_inputs import _season_requirements
from backend.services.datalayer.snapshot_sqlite import (
    ResolvedSnapshotMaterializationInput,
    SQLiteSnapshotMaterializer,
)
from backend.services.datalayer.sleeper.scope import EndpointKind
from backend.tests.services.datalayer.test_snapshot_sqlite_v3 import _materialization


def test_preseason_snapshot_keeps_history_and_rosters_without_current_results(tmp_path: Path) -> None:
    original = _materialization()
    history, primary = original.inputs.seasons
    requirements = _season_requirements(primary.identity, 0, primary.settings)
    assert {entry.request.endpoint_kind for entry in requirements} == {
        EndpointKind.LEAGUE, EndpointKind.LEAGUE_USERS, EndpointKind.LEAGUE_ROSTERS,
    }
    primary_scopes = {entry.request.scope_key for entry in requirements}
    excluded = set(primary.requirement_scopes) - primary_scopes
    inputs = original.inputs.model_copy(update={
        "primary": original.inputs.primary.model_copy(update={"through_week": 0}),
        "seasons": (history, primary.model_copy(update={
            "through_week": 0,
            "requirement_scopes": tuple(entry.request.scope_key for entry in requirements),
        })),
        "requirements": original.inputs.requirements.model_copy(update={
            "entries": tuple(entry for entry in original.inputs.requirements.entries
                             if entry.request.scope_key not in excluded),
        }),
        "manifest": original.inputs.manifest.model_copy(update={
            "entries": tuple(entry for entry in original.inputs.manifest.entries
                             if entry.scope_key not in excluded),
        }),
    })
    materialization = ResolvedSnapshotMaterializationInput.model_validate({
        "inputs": inputs.model_dump(),
        "build_key": original.build_key,
        "endpoint_records": tuple(entry for entry in original.endpoint_records
                                  if entry.manifest_entry.scope_key not in excluded),
    })
    artifact = SQLiteSnapshotMaterializer(tmp_path / "staging").materialize(materialization)
    with sqlite3.connect(artifact.path) as connection:
        connection.row_factory = sqlite3.Row
        for table in ("matchups", "player_performances", "games", "standings", "transactions"):
            assert connection.execute(
                f"SELECT count(*) FROM {table} WHERE league_id='league-2026'"
            ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM matchups WHERE league_id='league-2025'"
        ).fetchone()[0] > 0
        assert connection.execute(
            "SELECT count(*) FROM roster_players WHERE league_id='league-2026'"
        ).fetchone()[0] > 0
        result = get_league_snapshot(connection, "league-2026", "2026", 0)
        assert result["competition_phase"] == "preseason"
        assert result["standings"] == []
        assert result["games"] == []
    ready = ReadyDataSnapshot(
        id=uuid4(), competition_id=primary.identity.competition_id,
        primary_competition_season_id=primary.identity.competition_season_id,
        through_week=0, as_of_date=inputs.primary.as_of_date,
        build_key=materialization.build_key, snapshot_projection_version="3",
        input_revision=inputs.input_revision,
        completeness_warnings=artifact.completeness_warnings,
        artifact=VerifiedLocalArtifact(
            path=artifact.path.resolve(),
            storage_key=f"snapshots/sha256/{artifact.sha256[:2]}/{artifact.sha256}.sqlite",
            sha256=artifact.sha256, byte_length=artifact.byte_length,
        ),
        included_seasons=tuple(ReadySnapshotSeason(
            competition_season_id=season.identity.competition_season_id,
            sleeper_league_id=season.identity.sleeper_league_id,
            season_year=season.identity.season_year,
            sequence_number=season.identity.sequence_number,
            role=season.role.value, through_week=season.through_week,
        ) for season in inputs.seasons),
    )
    with FrozenLeagueData.open(ready) as data:
        assert data.get_week_games() == []
        assert data.get_league_snapshot()["competition_phase"] == "preseason"
        assert data.get_week_games(week=1, season=2025)
        with pytest.raises(ValueError, match="0 through 0"):
            data.get_week_games(week=1, season=2026)


def test_preseason_does_not_request_brackets_when_playoff_settings_unknown() -> None:
    primary = _materialization().inputs.seasons[-1]
    requirements = _season_requirements(
        primary.identity, 0, primary.settings.model_copy(update={"playoff_start_week": None}),
    )
    assert not any(entry.request.endpoint_kind in {
        EndpointKind.MATCHUPS, EndpointKind.TRANSACTIONS,
        EndpointKind.WINNERS_BRACKET, EndpointKind.LOSERS_BRACKET,
    } for entry in requirements)
