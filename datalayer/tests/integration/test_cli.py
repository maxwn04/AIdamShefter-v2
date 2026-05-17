import json
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


def test_cli_snapshot_writes_file(monkeypatch, tmp_path: Path):
    class DummyData:
        def __init__(self, league_id=None):
            self.league_id = league_id or "123"

        def load(self):
            pass

        def save_to_file(self, output_path: str) -> str:
            Path(output_path).write_text("snapshot", encoding="utf-8")
            return output_path

    monkeypatch.setattr(cli, "SleeperLeagueData", DummyData)

    output_path = tmp_path / "run.sqlite"
    exit_code = cli.main(
        ["snapshot", "--league-id", "123", "--output", str(output_path)]
    )

    assert exit_code == 0
    assert output_path.exists()


def test_cli_load_writes_cache(monkeypatch, tmp_path: Path):
    class DummyData:
        def __init__(self, league_id=None):
            self.league_id = league_id or "123"

        def load(self):
            pass

        def save_to_file(self, output_path: str) -> str:
            Path(output_path).write_text("cache", encoding="utf-8")
            return output_path

    monkeypatch.setattr(cli, "SleeperLeagueData", DummyData)

    output_path = tmp_path / "cache.sqlite"
    exit_code = cli.main(["load", "--league-id", "123", "--output", str(output_path)])

    assert exit_code == 0
    assert output_path.exists()


def test_cli_load_reuses_recent_cache(monkeypatch, tmp_path: Path, capsys):
    class DummyData:
        def __init__(self, league_id=None):
            self.league_id = league_id or "123"

        def load(self):
            raise AssertionError("load() should not be called for recent cache")

    monkeypatch.setattr(cli, "SleeperLeagueData", DummyData)

    output_path = tmp_path / "cache.sqlite"
    output_path.write_text("cache", encoding="utf-8")
    exit_code = cli.main(["load", "--league-id", "123", "--output", str(output_path)])

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == str(output_path)


def test_cli_tools_prints_tool_schemas(capsys):
    exit_code = cli.main(["tools"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    tool_names = {tool["function"]["name"] for tool in payload}
    assert "standings" in tool_names
    assert "run_sql" in tool_names


def test_cli_tool_uses_snapshot_without_loading(monkeypatch, tmp_path: Path, capsys):
    class DummyData:
        @classmethod
        def from_file(cls, path: str):
            assert path == str(snapshot_path)
            return cls()

        def __init__(self, league_id=None):
            self.league_id = league_id or "123"

        def load(self):
            raise AssertionError("load() should not be called for snapshot-backed tools")

        def get_standings(self, week=None):
            return {"found": True, "as_of_week": week, "standings": []}

    snapshot_path = tmp_path / "run.sqlite"
    snapshot_path.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(cli, "SleeperLeagueData", DummyData)

    exit_code = cli.main(
        [
            "tool",
            "standings",
            "--snapshot",
            str(snapshot_path),
            "--args-json",
            '{"week": 1}',
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"found": True, "as_of_week": 1, "standings": []}


def test_cli_query_uses_snapshot_with_key_value_args(
    monkeypatch, tmp_path: Path, capsys
):
    class DummyData:
        @classmethod
        def from_file(cls, path: str):
            assert path == str(snapshot_path)
            return cls()

        def __init__(self, league_id=None):
            self.league_id = league_id or "123"

        def load(self):
            raise AssertionError("load() should not be called when snapshot exists")

        def get_standings(self, week=None):
            return {"found": True, "as_of_week": week, "standings": []}

    snapshot_path = tmp_path / "cache.sqlite"
    snapshot_path.write_text("cache", encoding="utf-8")
    monkeypatch.setattr(cli, "SleeperLeagueData", DummyData)

    exit_code = cli.main(
        ["query", "standings", "week=2", "--snapshot", str(snapshot_path)]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"found": True, "as_of_week": 2, "standings": []}


def test_cli_tool_rejects_invalid_json(capsys):
    exit_code = cli.main(["tool", "standings", "--args-json", "{"])

    assert exit_code == 2
    assert "--args-json must be valid JSON" in capsys.readouterr().err


def test_cli_tool_rejects_unknown_tool(capsys):
    exit_code = cli.main(["tool", "not_a_tool", "--args-json", "{}"])

    assert exit_code == 2
    assert "Unknown tool: not_a_tool" in capsys.readouterr().err


def test_cli_tool_rejects_missing_required_args(capsys):
    exit_code = cli.main(["tool", "team_dossier", "--args-json", "{}"])

    assert exit_code == 2
    assert "Missing required parameter" in capsys.readouterr().err


def test_cli_tool_rejects_missing_snapshot(tmp_path: Path, capsys):
    missing_path = tmp_path / "missing.sqlite"
    exit_code = cli.main(
        ["tool", "standings", "--snapshot", str(missing_path), "--args-json", "{}"]
    )

    assert exit_code == 1
    assert "Snapshot not found" in capsys.readouterr().err
