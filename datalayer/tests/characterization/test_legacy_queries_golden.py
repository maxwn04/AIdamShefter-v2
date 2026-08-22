import json
from pathlib import Path

import pytest

from datalayer.sleeper_data.config import SleeperConfig
from datalayer.sleeper_data.sleeper_league_data import SleeperLeagueData
from datalayer.tests.characterization.legacy_outputs import collect_query_golden


GOLDEN_PATH = Path(__file__).parent / "golden" / "legacy_query_outputs.json"


def test_legacy_curated_queries_and_resolution_match_golden(
    monkeypatch_sleeper_api,
) -> None:
    data = _load(week_override=None)
    playoff_data = _load(week_override=15)
    try:
        actual = collect_query_golden(data, playoff_data)
    finally:
        _close(data)
        _close(playoff_data)

    expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert actual == expected


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM players",
        "PRAGMA table_info(players)",
        "SELECT * FROM players; DROP TABLE players",
    ],
)
def test_legacy_sql_guard_rejects_non_select_behavior(
    monkeypatch_sleeper_api,
    statement: str,
) -> None:
    data = _load(week_override=None)
    try:
        with pytest.raises(ValueError):
            data.run_sql(statement)
    finally:
        _close(data)


def _load(*, week_override: int | None) -> SleeperLeagueData:
    data = SleeperLeagueData(
        config=SleeperConfig(league_id="123", week_override=week_override)
    )
    data.load()
    return data


def _close(data: SleeperLeagueData) -> None:
    data._conn().close()
    if data.engine is not None:
        data.engine.dispose()
