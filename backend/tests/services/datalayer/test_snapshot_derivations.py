from decimal import Decimal
from pathlib import Path

import pytest

from backend.services.datalayer import FrozenLeagueData
from backend.services.datalayer.snapshot_sqlite import (
    SQLiteSnapshotMaterializer,
    derive_snapshot_rows,
    project_source_records,
)
from backend.services.datalayer.sleeper.endpoints import (
    LeagueEndpointRecords,
    LeagueRostersEndpointRecords,
    MatchupsEndpointRecords,
    NflStateEndpointRecords,
)
from backend.tests.services.datalayer.test_snapshot_source_projection import (
    _fixture_input,
)


def _derived(materialization=None):
    materialization = materialization or _fixture_input()
    return derive_snapshot_rows(
        materialization,
        project_source_records(materialization),
    )


def test_derives_games_and_weekly_standings_from_selected_matchups() -> None:
    projection = _derived()

    games = projection.rows_for("games")
    assert len(games) == 2
    assert [row["winner_roster_id"] for row in games] == [1, 1]
    standings = [row for row in projection.rows_for("standings") if row["week"] == 2]
    assert [(row["roster_id"], row["wins"], row["rank"]) for row in standings] == [
        (1, 2, 1),
        (2, 0, 2),
    ]
    assert standings[0]["points_for"] == 210.5
    assert standings[0]["streak_type"] == "W"
    assert standings[0]["streak_len"] == 2


def test_derives_profiles_picks_and_deterministic_season_context() -> None:
    projection = _derived()

    profiles = projection.rows_for("team_profiles")
    assert [(row["team_name"], row["manager_name"]) for row in profiles] == [
        ("Alpha", "Alice"),
        ("Beta", "Bob"),
    ]
    picks = projection.rows_for("draft_picks")
    assert len(picks) == 12
    traded = [row for row in picks if row["source"] == "trade"]
    assert traded == [
        {
            "league_id": "123",
            "season": "2025",
            "round": 1,
            "original_roster_id": 1,
            "current_roster_id": 2,
            "pick_id": None,
            "source": "trade",
        }
    ]
    assert projection.rows_for("season_context") == (
        {
            "league_id": "123",
            "computed_week": 2,
            "override_week": 2,
            "effective_week": 2,
            "generated_at": None,
        },
    )
    assert projection.rows_for("roster_identities") == (
        {
            "league_id": "123",
            "roster_id": 1,
            "competition_id": "22222222-2222-2222-2222-222222222222",
            "competition_season_id": "11111111-1111-1111-1111-111111111111",
            "season_roster_id": "00000000-0000-0000-0000-000000000065",
            "franchise_id": "00000000-0000-0000-0000-0000000000c9",
        },
        {
            "league_id": "123",
            "roster_id": 2,
            "competition_id": "22222222-2222-2222-2222-222222222222",
            "competition_season_id": "11111111-1111-1111-1111-111111111111",
            "season_roster_id": "00000000-0000-0000-0000-000000000066",
            "franchise_id": "00000000-0000-0000-0000-0000000000ca",
        },
    )


def test_malformed_matchup_group_is_omitted_with_warning() -> None:
    materialization = _fixture_input()
    endpoints = list(materialization.endpoint_records)
    index = next(
        i
        for i, endpoint in enumerate(endpoints)
        if isinstance(endpoint.records, MatchupsEndpointRecords)
        and endpoint.records.matchups[0].week == 2
    )
    endpoint = endpoints[index]
    records = endpoint.records.model_copy(
        update={"matchups": endpoint.records.matchups[:1]}
    )
    endpoints[index] = endpoint.model_copy(update={"records": records})
    changed = materialization.model_copy(update={"endpoint_records": tuple(endpoints)})

    projection = _derived(changed)

    assert len(projection.rows_for("games")) == 1
    assert "snapshot.matchup_group_omitted" in {
        warning.code for warning in projection.warnings
    }


def test_league_average_record_prefix_drives_standings() -> None:
    materialization = _fixture_input()
    endpoints = list(materialization.endpoint_records)
    index = next(
        i
        for i, endpoint in enumerate(endpoints)
        if isinstance(endpoint.records, LeagueRostersEndpointRecords)
    )
    endpoint = endpoints[index]
    records = endpoint.records.model_copy(
        update={
            "rosters": tuple(
                roster.model_copy(
                    update={"record_string": "WWWW" if position == 0 else "LLLL"}
                )
                for position, roster in enumerate(endpoint.records.rosters)
            )
        }
    )
    endpoints[index] = endpoint.model_copy(update={"records": records})
    changed = materialization.model_copy(
        update={
            "planning_context": materialization.planning_context.model_copy(
                update={"league_average_match": 1}
            ),
            "endpoint_records": tuple(endpoints),
        }
    )

    projection = _derived(changed)
    week_two = [row for row in projection.rows_for("standings") if row["week"] == 2]

    assert [(row["wins"], row["losses"]) for row in week_two] == [(4, 0), (0, 4)]
    assert "snapshot.league_average_record_incomplete" not in {
        warning.code for warning in projection.warnings
    }


def test_playoff_week_carries_forward_regular_standings() -> None:
    materialization = _fixture_input()
    changed = materialization.model_copy(
        update={
            "planning_context": materialization.planning_context.model_copy(
                update={"playoff_start_week": 2}
            )
        }
    )

    projection = _derived(changed)
    week_one = [row for row in projection.rows_for("standings") if row["week"] == 1]
    week_two = [row for row in projection.rows_for("standings") if row["week"] == 2]

    assert [row["wins"] for row in week_two] == [row["wins"] for row in week_one]
    assert [row["points_for"] for row in week_two] == [
        row["points_for"] for row in week_one
    ]
    assert [row["is_playoffs"] for row in projection.rows_for("games")] == [0, 1]


def _completion_input(*, last_scored: int | None, zero_scores: bool = True,
                      record_string: str | None = None, league_average: int = 0):
    materialization = _fixture_input()
    endpoints = []
    for endpoint in materialization.endpoint_records:
        records = endpoint.records
        if isinstance(records, LeagueEndpointRecords):
            settings = dict(records.league.provider_settings)
            settings.pop("last_scored_leg", None)
            if last_scored is not None:
                settings["last_scored_leg"] = last_scored
            records = records.model_copy(update={"league": records.league.model_copy(
                update={"provider_settings": settings}
            )})
        elif isinstance(records, MatchupsEndpointRecords) and zero_scores:
            records = records.model_copy(update={"matchups": tuple(
                matchup.model_copy(update={"points": Decimal("0")})
                for matchup in records.matchups
            )})
        elif isinstance(records, LeagueRostersEndpointRecords):
            records = records.model_copy(update={"rosters": tuple(
                roster.model_copy(update={"record_string": record_string})
                for roster in records.rosters
            )})
        endpoints.append(endpoint.model_copy(update={"records": records}))
    return materialization.model_copy(update={
        "endpoint_records": tuple(endpoints),
        "planning_context": materialization.planning_context.model_copy(
            update={"league_average_match": league_average}
        ),
    })


@pytest.mark.parametrize("last_scored", [None, 0])
@pytest.mark.parametrize("zero_scores", [False, True])
def test_unplayed_or_unknown_games_never_infer_completion_from_scores(
    last_scored: int | None, zero_scores: bool,
) -> None:
    projection = _derived(_completion_input(
        last_scored=last_scored, zero_scores=zero_scores,
    ))
    assert len(projection.rows_for("matchups")) == 4
    assert projection.rows_for("games") == ()
    assert all(
        (row["wins"], row["losses"], row["ties"], row["points_for"],
         row["rank"], row["streak_type"], row["streak_len"])
        == (0, 0, 0, 0, None, None, None)
        for row in projection.rows_for("standings")
    )
    assert "snapshot.matchup_completion_unknown" in {
        warning.code for warning in projection.warnings
    }


def test_completed_zero_score_ties_survive_with_explicit_completion() -> None:
    projection = _derived(_completion_input(last_scored=1))
    assert len(projection.rows_for("games")) == 1
    game = projection.rows_for("games")[0]
    assert (game["points_a"], game["points_b"], game["winner_roster_id"]) == (0, 0, None)
    assert all(
        (row["wins"], row["losses"], row["ties"], row["streak_type"], row["streak_len"])
        == (0, 0, 1, "T", 1)
        for row in projection.rows_for("standings")
    )


def test_regular_record_prefix_can_confirm_completed_zero_tie() -> None:
    projection = _derived(_completion_input(last_scored=None, record_string="T"))
    assert len(projection.rows_for("games")) == 1
    assert all(row["ties"] == 1 for row in projection.rows_for("standings"))


@pytest.mark.parametrize("last_scored", [None, 1])
def test_completed_historical_season_does_not_complete_post_final_placeholders(
    last_scored: int | None,
) -> None:
    materialization = _completion_input(last_scored=last_scored, record_string="T")
    endpoints = []
    for endpoint in materialization.endpoint_records:
        records = endpoint.records
        if isinstance(records, LeagueEndpointRecords):
            records = records.model_copy(update={"league": records.league.model_copy(
                update={"status": "complete"}
            )})
        elif isinstance(records, NflStateEndpointRecords):
            records = records.model_copy(update={"state": records.state.model_copy(
                update={"season": "2026", "week": 10, "season_type": "regular"}
            )})
        endpoints.append(endpoint.model_copy(update={"records": records}))
    projection = _derived(materialization.model_copy(update={
        "endpoint_records": tuple(endpoints),
        "planning_context": materialization.planning_context.model_copy(
            update={"playoff_start_week": 2}
        ),
    }))
    assert [game["week"] for game in projection.rows_for("games")] == [1]
    assert all(row["ties"] == 1 for row in projection.rows_for("standings"))
    assert "snapshot.matchup_completion_unknown" in {
        warning.code for warning in projection.warnings
    }


def test_league_average_record_does_not_include_unscored_future_prefix() -> None:
    projection = _derived(_completion_input(
        last_scored=1, record_string="TTWW", league_average=1,
    ))
    assert len(projection.rows_for("games")) == 1
    assert all(
        (row["wins"], row["ties"], row["streak_len"]) == (0, 2, 2)
        for row in projection.rows_for("standings")
    )
    unplayed = _derived(_completion_input(
        last_scored=0, record_string="TTWW", league_average=1,
    ))
    assert all(
        (row["wins"], row["ties"], row["rank"]) == (0, 0, None)
        for row in unplayed.rows_for("standings")
    )


def test_frozen_queries_do_not_backfill_unplayed_points_or_invent_ranks(tmp_path: Path) -> None:
    from backend.tests.services.datalayer.test_frozen_query_runtime import _ready

    materialization = _completion_input(last_scored=0, zero_scores=False)
    artifact = SQLiteSnapshotMaterializer(tmp_path / "evidence-unplayed").materialize(
        materialization
    )
    with FrozenLeagueData.open(_ready(materialization, artifact)) as data:
        standings = data.get_standings()["standings"]
        history = data.get_franchise_history("1")
        games = data.get_week_games(1)
        assert "snapshot.matchup_completion_unknown" in {
            warning.code for warning in data.completeness_warnings()
        }
    with pytest.raises(RuntimeError, match="closed"):
        data.completeness_warnings()
    assert games == []
    assert all(row["rank"] is None and row["points_for"] == 0 for row in standings)
    assert history["seasons"][0]["standing"]["record"] == "0-0"
    assert history["seasons"][0]["standing"]["rank"] is None
