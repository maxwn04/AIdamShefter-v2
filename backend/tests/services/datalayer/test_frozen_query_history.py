from __future__ import annotations

from pathlib import Path

import pytest

from backend.services.datalayer import (
    FrozenLeagueData,
    ReadyDataSnapshot,
    VerifiedLocalArtifact,
)
from backend.tests.services.datalayer.test_frozen_query_runtime import (
    _mutated_copy,
    _mutated_copy_many,
    ready_snapshot,
    v3_ready_snapshot,
)
from backend.tests.services.datalayer.test_snapshot_sqlite_v3 import (
    SECOND_FRANCHISE_ID,
    SHARED_FRANCHISE_ID,
)


def test_league_history_is_deterministic_oldest_to_primary(
    v3_ready_snapshot: ReadyDataSnapshot,
) -> None:
    with FrozenLeagueData.open(v3_ready_snapshot) as data:
        first = data.get_league_history()
        second = data.get_league_history()

    assert first == second
    assert first["found"] is True
    assert first["primary_season"] == 2026
    assert [season["season"] for season in first["seasons"]] == [2025, 2026]
    assert [season["league_name"] for season in first["seasons"]] == [
        "League 2025",
        "League 2026",
    ]
    assert [season["through_week"] for season in first["seasons"]] == [18, 3]
    assert [season["team_count"] for season in first["seasons"]] == [2, 2]


def test_franchise_history_survives_changed_roster_and_names(
    v3_ready_snapshot: ReadyDataSnapshot,
    tmp_path: Path,
) -> None:
    changed = _changed_franchise_artifact(v3_ready_snapshot, tmp_path)
    ready = v3_ready_snapshot.model_copy(update={"artifact": changed})

    with FrozenLeagueData.open(ready) as data:
        by_uuid = data.get_franchise_history(str(SHARED_FRANCHISE_ID))
        by_primary_roster = data.get_franchise_history("1")
        by_primary_name = data.get_franchise_history("Current Guard")
        historical_name = data.get_franchise_history("Old Guard")
        unknown_uuid = data.get_franchise_history(
            "40000000-0000-0000-0000-000000000001"
        )

    assert by_uuid == by_primary_roster == by_primary_name
    assert by_uuid["found"] is True
    assert by_uuid["franchise_id"] == str(SHARED_FRANCHISE_ID)
    assert [season["season"] for season in by_uuid["seasons"]] == [2025, 2026]
    assert [season["sleeper_roster_id"] for season in by_uuid["seasons"]] == [
        "7",
        "1",
    ]
    assert [season["team_name"] for season in by_uuid["seasons"]] == [
        "Old Guard",
        "Current Guard",
    ]
    assert [season["manager_name"] for season in by_uuid["seasons"]] == [
        "Old Manager",
        "Current Manager",
    ]
    assert all(season["standing"] is not None for season in by_uuid["seasons"])
    assert historical_name == {"found": False, "roster_key": "Old Guard"}
    assert unknown_uuid == {
        "found": False,
        "franchise_id": "40000000-0000-0000-0000-000000000001",
    }


def test_franchise_history_preserves_primary_ambiguity(
    v3_ready_snapshot: ReadyDataSnapshot,
    tmp_path: Path,
) -> None:
    changed = _changed_franchise_artifact(v3_ready_snapshot, tmp_path)
    ambiguous = _mutated_copy(
        changed.path,
        tmp_path / "ambiguous-primary-name.sqlite",
        "UPDATE team_profiles SET team_name = 'Current Guard' "
        "WHERE league_id = 'league-2026' AND roster_id = 2",
    )
    with FrozenLeagueData.open(
        v3_ready_snapshot.model_copy(update={"artifact": ambiguous})
    ) as data:
        result = data.get_franchise_history("Current Guard")

    assert result["found"] is False
    assert result["roster_key"] == "Current Guard"
    assert len(result["matches"]) == 2


def test_history_handles_reach_exact_historical_and_current_rosters(
    v3_ready_snapshot: ReadyDataSnapshot,
    tmp_path: Path,
) -> None:
    changed = _changed_franchise_artifact(v3_ready_snapshot, tmp_path)
    populated = _mutated_copy_many(
        changed.path,
        tmp_path / "evidence-history-rosters.sqlite",
        (
            ("INSERT INTO roster_players VALUES ('league-2025', 7, 'p1', 'starter')", ()),
            ("INSERT INTO roster_players VALUES ('league-2026', 1, 'p2', 'starter')", ()),
        ),
    )
    with FrozenLeagueData.open(
        v3_ready_snapshot.model_copy(update={"artifact": populated})
    ) as data:
        history = data.get_franchise_history("Current Guard")
        historical, current = history["seasons"]
        old_roster = data.get_roster_at_cutoff(**historical["roster_lookup"])
        new_roster = data.get_roster_at_cutoff(**current["roster_lookup"])
        identity = data.resolve_roster_identity(**historical["roster_lookup"])
        wrong_season = data.get_roster_at_cutoff(
            historical["season_roster_id"], season=2026
        )
        guessed_name = data.get_roster_at_cutoff("Current Guard", season=2025)

    assert old_roster["found"] is new_roster["found"] is True
    assert old_roster["team"]["team_name"] == "Old Guard"
    assert new_roster["team"]["team_name"] == "Current Guard"
    assert old_roster["roster"] != new_roster["roster"]
    assert any(old_roster["roster"]["starters"].values())
    assert any(new_roster["roster"]["starters"].values())
    assert str(identity.identity.season_roster_id) == historical["season_roster_id"]
    assert identity.identity.sleeper_roster_id == "7"
    assert wrong_season["found"] is guessed_name["found"] is False


def test_franchise_history_omits_seasons_without_an_appearance(
    v3_ready_snapshot: ReadyDataSnapshot,
    tmp_path: Path,
) -> None:
    historical_only = _mutated_copy_many(
        v3_ready_snapshot.artifact.path,
        tmp_path / "historical-only-franchise.sqlite",
        (
            (
                "DELETE FROM roster_identities WHERE league_id = ? AND roster_id = 2",
                ("league-2026",),
            ),
            (
                "DELETE FROM rosters WHERE league_id = ? AND roster_id = 2",
                ("league-2026",),
            ),
            (
                "DELETE FROM team_profiles WHERE league_id = ? AND roster_id = 2",
                ("league-2026",),
            ),
        ),
    )
    with FrozenLeagueData.open(
        v3_ready_snapshot.model_copy(update={"artifact": historical_only})
    ) as data:
        result = data.get_franchise_history(str(SECOND_FRANCHISE_ID))

    assert result["found"] is True
    assert [season["season"] for season in result["seasons"]] == [2025]


def test_v2_history_contracts_degrade_to_one_primary_season(
    ready_snapshot: ReadyDataSnapshot,
) -> None:
    with FrozenLeagueData.open(ready_snapshot) as data:
        league = data.get_league_history()
        franchise = data.get_franchise_history("1")

    assert league["found"] is True
    assert league["primary_season"] == league["seasons"][0]["season"]
    assert len(league["seasons"]) == 1
    assert franchise["found"] is True
    assert len(franchise["seasons"]) == 1
    assert franchise["seasons"][0]["role"] == "primary"


@pytest.mark.parametrize("bracket_type,is_champion", [("winners", True), ("losers", False)])
def test_championship_requires_winners_bracket_final(
    ready_snapshot: ReadyDataSnapshot, tmp_path: Path,
    bracket_type: str, is_champion: bool,
) -> None:
    changed = _mutated_copy_many(
        ready_snapshot.artifact.path,
        tmp_path / f"evidence-{bracket_type}-final.sqlite",
        ((
            "INSERT INTO playoff_matchups (league_id, season, bracket_type, node_key, "
            "round, matchup_id, t1_roster_id, t2_roster_id, winner_roster_id, "
            "loser_roster_id, placement) VALUES ('123', '2024', ?, 'final', 1, 1, 1, 2, 1, 2, 1)",
            (bracket_type,),
        ),),
    )
    with FrozenLeagueData.open(ready_snapshot.model_copy(update={"artifact": changed})) as data:
        path = data.get_team_playoff_path("Alpha")
        bracket = data.get_playoff_bracket(bracket_type)["brackets"][bracket_type]
    assert path["is_champion"] is is_champion
    assert path["matchups"][0]["bracket_type"] == bracket_type
    assert bracket["champion"] == ("Alpha" if is_champion else None)


def _changed_franchise_artifact(
    ready: ReadyDataSnapshot,
    tmp_path: Path,
) -> VerifiedLocalArtifact:
    return _mutated_copy_many(
        ready.artifact.path,
        tmp_path / "changed-franchise.sqlite",
        (
            (
                "UPDATE rosters SET roster_id = 7 "
                "WHERE league_id = 'league-2025' AND roster_id = 1",
                (),
            ),
            (
                "UPDATE roster_identities SET roster_id = 7 "
                "WHERE league_id = 'league-2025' AND roster_id = 1",
                (),
            ),
            (
                "UPDATE team_profiles SET roster_id = 7, "
                "team_name = 'Old Guard', manager_name = 'Old Manager' "
                "WHERE league_id = 'league-2025' AND roster_id = 1",
                (),
            ),
            (
                "UPDATE standings SET roster_id = 7 "
                "WHERE league_id = 'league-2025' AND roster_id = 1",
                (),
            ),
            (
                "UPDATE team_profiles SET team_name = 'Current Guard', "
                "manager_name = 'Current Manager' "
                "WHERE league_id = 'league-2026' AND roster_id = 1",
                (),
            ),
        ),
    )
