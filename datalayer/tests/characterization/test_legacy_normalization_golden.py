import json
from pathlib import Path

from datalayer.sleeper_data.config import SleeperConfig
from datalayer.sleeper_data.sleeper_league_data import SleeperLeagueData
from datalayer.tests.characterization.legacy_outputs import (
    collect_normalization_golden,
)


GOLDEN_PATH = Path(__file__).parent / "golden" / "legacy_normalized_tables.json"


def test_legacy_normalization_and_derivations_match_golden(
    monkeypatch_sleeper_api,
    sleeper_fixtures,
) -> None:
    data = SleeperLeagueData(
        config=SleeperConfig(league_id="123", week_override=None)
    )
    data.load()
    try:
        actual = collect_normalization_golden(data, sleeper_fixtures)
    finally:
        _close(data)

    expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert actual == expected


def _close(data: SleeperLeagueData) -> None:
    data._conn().close()
    if data.engine is not None:
        data.engine.dispose()
