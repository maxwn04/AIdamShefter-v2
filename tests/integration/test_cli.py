from pathlib import Path

import datalayer.cli.main as cli


def test_cli_load_export_writes_file(monkeypatch, tmp_path: Path):
    class DummyData:
        def __init__(self, league_id=None):
            self.league_id = league_id or "123"
            self.loaded = False

        def load(self):
            self.loaded = True

        def save_to_file(self, output_path: str) -> str:
            Path(output_path).write_text("ok", encoding="utf-8")
            return output_path

    monkeypatch.setattr(cli, "SleeperLeagueData", DummyData)

    output_path = tmp_path / "snapshot.sqlite"
    exit_code = cli.main(
        ["load-export", "--league-id", "123", "--output", str(output_path)]
    )

    assert exit_code == 0
    assert output_path.exists()
