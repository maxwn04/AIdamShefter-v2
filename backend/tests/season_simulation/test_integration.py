"""Real PostgreSQL and ordinary reporter loop; only HTTP/provider/dump transport scripted."""

import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from alembic import command
import pytest
from sqlalchemy import create_engine, text

import backend.composition as composition
from backend.season_simulation import bootstrap
from backend.season_simulation.backend import DatabaseCampaignBackend
from backend.season_simulation.contracts import Campaign, CampaignProgress, PreparedInputs, RunLimits, StepProgress
from backend.season_simulation.controller import SeasonController
from backend.season_simulation.docker import DockerTarget
from backend.season_simulation.export import export_campaign, verify_export
from backend.season_simulation.freeze import archive_runtime, runtime_freeze
from backend.season_simulation.store import campaign_hash, load_campaign, save_progress, write_json
from backend.services.reporter.generator import generate_article
from backend.tests.database.conftest import _alembic_config, database_url
from backend.tests.season_simulation.test_bootstrap import ScriptedSleeperSource
from backend.tests.services.reporter.test_integration import make_response, tool_call


def fake_dump(target, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"scripted dump transport; actual Docker restore is separate smoke")
    return destination


def scripted_completion(week: int, *, save_memory: bool = False):
    calls = [
        ("league_snapshot", {"week": week}),
        ("save_fact", {"id": "score", "claim_text": f"One scored 10 points in week {week}.", "data_refs": [f"league_snapshot:week={week}"], "numbers": {"points": 10}, "category": "score"}),
        ("create_artifact", {"path": "article.md", "content": f"# Week {week}\n\nOne scored 10 points."}),
        ("submit_artifact", {"path": "article.md", "expected_revision": 1}),
    ]
    if save_memory:
        calls.append(("save_league_note", {"key": "opening", "value": "One opened with 10 points."}))
    calls.append(("complete_memory_review", {}))
    class BoundedCompletion:
        def __init__(self, responses):
            self.responses = responses
            self.requests = []

        async def __call__(self, **kwargs):
            self.requests.append(kwargs)
            if not self.responses:
                raise AssertionError("scripted responses exhausted: " + json.dumps(kwargs["messages"][-2:], default=str))
            response = self.responses[0]
            current = response.choices[0].message.tool_calls[0].function
            fact_schema = next(spec["function"]["parameters"] for spec in kwargs["tools"] if spec["function"]["name"] == "save_fact")
            if current.name == "save_fact" and "bindings" in fact_schema["properties"]:
                # The same mechanics fixture runs against both the frozen original
                # reporter and the combined evidence candidate. Follow only the
                # advertised tool schema and actual executed model-visible records.
                records = []
                for message in kwargs["messages"]:
                    if message.get("role") != "tool":
                        continue
                    try:
                        result = json.loads(message["content"])
                    except (ValueError, TypeError):
                        continue
                    if isinstance(result, dict):
                        records.extend({**result.get("scope", {}), **record} for record in result.get("records", []))
                selected = [(record, field) for record in records if record.get("subject") == "One"
                            for field, value in record.get("fields", {}).items()
                            if field in {"points", "points_for", "winner_points", "points_a", "points_b"}
                            and value == 10 and record.get("week_from") == record.get("week_to") == week]
                assert selected, "weekly One=10 evidence must be returned by the executed data tool"
                record, field = selected[0]
                binding = {key: record.get(key) for key in ("ref", "subject", "season", "week_from", "week_to", "perspective")}
                binding.update(field=field, value=record["fields"][field])
                args = json.loads(current.arguments)
                args.update(data_refs=[record["ref"]], bindings=[binding], numbers={field: 10})
                current.arguments = json.dumps(args)
            return self.responses.pop(0)
    return BoundedCompletion([make_response(tool_calls=[tool_call(name, args, f"w{week}-{i}")]) for i, (name, args) in enumerate(calls)])


def test_serial_normal_generations_reconcile_failure_noop_and_complete_export(database_url, tmp_path, monkeypatch):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.delenv("AIDAM_MIGRATION_DATABASE_URL", raising=False)
    monkeypatch.setenv("AIDAM_MIGRATION_REQUIRE_TLS", "false")
    monkeypatch.setenv("AIDAM_MIGRATION_ROLE", "aidam_owner")
    command.upgrade(_alembic_config(database_url), "head")
    monkeypatch.setattr(composition, "SleeperSourceClient", ScriptedSleeperSource)
    monkeypatch.setattr(bootstrap, "verify_target", lambda _: None)
    monkeypatch.setattr(bootstrap, "target_environment", lambda _: {"AIDAM_MIGRATION_DATABASE_URL": database_url})
    monkeypatch.setattr(bootstrap, "dump_database", fake_dump)
    target = DockerTarget("aidam-season-test", "test", "test", 55441, "aidam", "env", str(tmp_path))
    prepared = bootstrap.prepare_target(target, league_id="123", season_year=2025, first_week=1, last_week=3,
        first_cutoff=datetime(2025, 9, 9, 12, tzinfo=UTC), model="openai/gpt-4o-mini")
    inputs = PreparedInputs.model_validate_json(prepared.read_text())
    monkeypatch.setenv("AIDAM_DATALAYER_ROOT", str(inputs.data_root))
    engine = create_engine(database_url)
    backend = DatabaseCampaignBackend(engine, inputs.competition_id)
    directory = tmp_path / "campaign"
    directory.mkdir()
    root = backend.revision_manager.ensure_current()
    campaign = Campaign(campaign_id=uuid4(), inputs=inputs, root_revision_id=root.revision_id,
        root_state_hash=root.state_content_hash, target_identity="test", runtime=runtime_freeze())
    archive_runtime(campaign.runtime, directory / "runtime")
    write_json(directory / "campaign.json", campaign.model_dump(mode="json"))
    progress = CampaignProgress(campaign_hash=campaign_hash(campaign), steps=tuple(StepProgress() for _ in inputs.steps))
    save_progress(directory, progress)
    seen = []
    fail_third = True
    async def reporter(data, config, **kwargs):
        week = config.time_range.week_end
        seen.append((week, kwargs["memory_context"].pinned_revision_id))
        with pytest.raises(ValueError):
            data.get_league_snapshot(week=week + 1)
        if week == 3 and fail_third:
            raise RuntimeError("scripted week-three provider failure")
        return await generate_article(data, config, **kwargs, complete=scripted_completion(week, save_memory=week == 1))
    backend.dependencies.service._reporter = reporter
    exports = []
    def exporter(campaign, progress):
        exports.append(export_campaign(directory, campaign, progress, engine, target, dump=fake_dump))
    controller = SeasonController(directory, backend, export=exporter)
    try:
        result = asyncio.run(controller.run(RunLimits(max_steps=3)))
        assert result.state == "failed", result.detail
        rows = sorted(backend.generations(), key=lambda row: row.week_end)
        assert [row.status.value for row in rows] == ["succeeded", "succeeded", "failed"], [row.failure_summary for row in rows]
        assert len(backend.revisions()) == 2
        successful_head = backend.head()
        assert seen == [(1, root.revision_id), (2, successful_head), (3, successful_head)]
        fail_third = False
        assert asyncio.run(controller.run(RunLimits(max_steps=1, max_attempts_per_step=2), retry_failed=True)).state == "complete"
        assert len(backend.revisions()) == 2
        assert len(seen) == 4
        assert asyncio.run(controller.run(RunLimits(max_steps=3))).state == "complete"
        assert len(seen) == 4
        bundle = exports[-1]
        verify_export(bundle)
        index = json.loads((bundle / "season-index.json").read_text())
        assert len(index) == 4
        assert all((bundle / item["article"]).is_file() for item in index if item["status"] == "succeeded")
        no_op = next(item for item in index if item["week"] == 2)
        assert no_op["input_memory_revision_id"] == no_op["output_memory_revision_id"] == str(successful_head)
        ai_calls = json.loads((bundle / "tables/reporting.ai_calls.json").read_text())
        tools = json.loads((bundle / "tables/reporting.tool_calls.json").read_text())
        assert len(ai_calls) >= 16 and all(row["input_messages"] and row["tool_definitions"] and row["provider_response"] is not None for row in ai_calls)
        assert any(row["tool_name"] == "league_snapshot" and row["result_jsonb"] for row in tools)
        assert len(list((bundle / "data/snapshots").rglob("*.sqlite"))) == 3
        assert "research_brief.md" in (bundle / "tables/reporting.artifacts.json").read_text()
        assert len(json.loads((bundle / "usage.json").read_text())) == 4
        previous_latest = (directory / "exports/latest.json").read_bytes()
        def fail_dump(*args): raise OSError("scripted export transport failure")
        with pytest.raises(OSError):
            export_campaign(directory, campaign, load_campaign(directory)[1], engine, target, dump=fail_dump)
        assert (directory / "exports/latest.json").read_bytes() == previous_latest
        assert len(backend.generations()) == 4
        # Corruption is visible without the container.
        (bundle / "database.dump").write_bytes(b"corrupt")
        with pytest.raises(ValueError, match="corrupt"): verify_export(bundle)
    finally:
        backend.close()
        engine.dispose()
