from backend.services.datalayer.snapshot_sqlite import (
    derive_snapshot_rows,
    project_source_records,
)
from backend.services.datalayer.sleeper.endpoints import (
    LeagueRostersEndpointRecords,
    MatchupsEndpointRecords,
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
