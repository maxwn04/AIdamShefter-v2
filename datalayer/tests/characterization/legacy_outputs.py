"""Deterministic collectors for the legacy fixture-backed golden contracts."""

from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any

from sqlalchemy import text

from datalayer.sleeper_data.load import _record_string_to_weeks
from datalayer.sleeper_data.normalize import normalize_bracket
from datalayer.sleeper_data.schema import metadata
from datalayer.sleeper_data.sleeper_league_data import SleeperLeagueData


def collect_normalization_golden(
    data: SleeperLeagueData,
    sleeper_fixtures: dict[str, Any],
) -> dict[str, Any]:
    """Capture every loaded legacy row plus skipped bracket derivations."""

    connection = data._conn()
    tables: dict[str, list[dict[str, Any]]] = {}
    for table_name in sorted(metadata.tables):
        rows = [
            dict(row)
            for row in connection.execute(
                text(f'SELECT * FROM "{table_name}"')
            ).mappings()
        ]
        if table_name == "season_context":
            for row in rows:
                row.pop("generated_at", None)
        tables[table_name] = sorted(rows, key=_stable_json)

    brackets: dict[str, list[dict[str, Any]]] = {}
    for bracket_type in ("winners", "losers"):
        rows = normalize_bracket(
            sleeper_fixtures[f"{bracket_type}_bracket"],
            league_id="123",
            season="2024",
            bracket_type=bracket_type,
        )
        brackets[bracket_type] = [asdict(row) for row in rows]

    return _json_round_trip(
        {
            "tables": tables,
            "bracket_records": brackets,
            "record_string_weeks": {
                "single_result": _record_string_to_weeks("WLTW", chars_per_week=1),
                "median_double_result": _record_string_to_weeks(
                    "WWLTTW",
                    chars_per_week=2,
                ),
            },
        }
    )


def collect_query_golden(
    data: SleeperLeagueData,
    playoff_data: SleeperLeagueData,
) -> dict[str, Any]:
    """Capture every curated legacy query family and resolver route."""

    return _json_round_trip(
        {
            "league_snapshot": data.get_league_snapshot(week=2),
            "bench_analysis_league": data.get_bench_analysis(week=2),
            "bench_analysis_team": data.get_bench_analysis("Alpha", week=2),
            "standings": data.get_standings(week=2),
            "team_dossier_by_name": data.get_team_dossier("alpha", week=2),
            "team_dossier_by_manager": data.get_team_dossier("Alice", week=2),
            "team_dossier_by_id": data.get_team_dossier("1", week=2),
            "team_dossier_not_found": data.get_team_dossier("missing", week=2),
            "team_schedule": data.get_team_schedule("Alpha"),
            "week_games": data.get_week_games(week=2),
            "week_games_default": data.get_week_games(),
            "week_games_with_players": data.get_week_games_with_players(week=2),
            "team_game": data.get_team_game("Alpha", week=2),
            "team_game_with_players": data.get_team_game_with_players(
                "Alpha",
                week=2,
            ),
            "week_player_leaderboard": data.get_week_player_leaderboard(
                week=2,
                limit=3,
            ),
            "season_leaders": data.get_season_leaders(limit=3),
            "season_leaders_filtered": data.get_season_leaders(
                week_from=2,
                week_to=2,
                position="QB",
                roster_key="Alice",
                role="starter",
                sort_by="avg",
                limit=3,
            ),
            "transactions": data.get_transactions(1, 2),
            "team_transactions": data.get_team_transactions("Alpha", 1, 2),
            "week_transactions": data.get_week_transactions(week=2),
            "team_week_transactions": data.get_team_week_transactions(
                "Alpha",
                week_from=2,
            ),
            "player_summary_by_name": data.get_player_summary("player one"),
            "player_summary_by_id": data.get_player_summary("p1"),
            "player_summary_not_found": data.get_player_summary("missing"),
            "player_weekly_log": data.get_player_weekly_log("Player One"),
            "player_weekly_log_filtered": data.get_player_weekly_log(
                "p1",
                week_from=2,
                week_to=2,
            ),
            "roster_current_by_name": data.get_roster_current("Alpha"),
            "roster_current_by_manager": data.get_roster_current("Alice"),
            "roster_snapshot": data.get_roster_snapshot("1", week=1),
            "playoff_brackets": playoff_data.get_playoff_bracket(),
            "playoff_winners": playoff_data.get_playoff_bracket("winners"),
            "team_playoff_path": playoff_data.get_team_playoff_path("Alice"),
            "sql_named_params_and_limit": data.run_sql(
                "SELECT roster_id, points FROM matchups "
                "WHERE week = :week ORDER BY roster_id",
                {"week": 2},
                limit=1,
            ),
        }
    )


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_round_trip(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value, sort_keys=True))
