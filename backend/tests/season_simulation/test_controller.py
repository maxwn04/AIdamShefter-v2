from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from backend.resources.memory.revisions import CanonicalRevision
from backend.resources.reporting.generations import GenerationStatus
from backend.season_simulation.contracts import Campaign, CampaignProgress, PreparedInputs, PreparedStep, RunLimits, RuntimeFreeze, StepProgress
from backend.season_simulation.controller import SeasonController, reconcile
from backend.season_simulation.store import campaign_hash, load_campaign, save_progress, write_json
from backend.services.generations.service import _resolved_settings
from backend.tests.services.generations.test_service import _generation


class FakeBackend:
    def __init__(self, campaign):
        self.campaign = campaign
        self.rows = {}
        self.history = [CanonicalRevision(revision_id=campaign.root_revision_id, competition_id=campaign.inputs.competition_id,
                                         sequence_number=0, state_content_hash=campaign.root_state_hash, created_at=datetime.now(UTC))]
        self.calls = []
        self.fail = False
        self.noop = False
        self.missing = False
        self.tokens = 0
        self.usage_complete = True

    def lock(self): return nullcontext()
    def generations(self): return tuple(self.rows.values())
    def revisions(self): return tuple(self.history)
    def head(self): return self.history[-1].revision_id
    def validate_inputs(self, campaign):
        if self.missing: raise ValueError("missing prepared input")
    def usage(self, ids): return self.tokens, Decimal("0"), self.usage_complete
    def submit(self, request):
        assert request.generation_id not in self.rows
        self.rows[request.generation_id] = _generation(
            generation_id=request.generation_id, competition_id=request.competition_id,
            season_id=request.competition_season_id, kind=request.kind, settings=_resolved_settings(request.settings),
            request_text=request.request_text, week_start=request.week_start, week_end=request.week_end,
            model=request.requested_primary_model, rerun_of_generation_id=request.rerun_of_generation_id)
    async def execute(self, gid):
        self.calls.append(gid)
        row = self.rows[gid]
        pin = row.settings["prepared_execution"]
        assert UUID(pin["expected_memory_revision_id"]) == self.head()
        self.rows[gid] = row.model_copy(update={
            "status": GenerationStatus.FAILED if self.fail else GenerationStatus.SUCCEEDED,
            "input_memory_revision_id": self.head(), "data_snapshot_id": UUID(pin["data_snapshot_id"]),
            "submitted_artifact_version_id": None if self.fail else uuid4(),
            "failure_summary": "scripted failure" if self.fail else None})
        if not self.fail and not self.noop:
            self.history.append(CanonicalRevision(revision_id=uuid4(), competition_id=row.competition_id,
                previous_revision_id=self.head(), sequence_number=len(self.history), producing_generation_id=gid,
                competition_season_id=row.competition_season_id, week=row.week_end,
                state_content_hash="b" * 64, created_at=datetime.now(UTC)))


@pytest.fixture
def setup(tmp_path):
    campaign = Campaign(campaign_id=uuid4(), root_revision_id=uuid4(), root_state_hash="a" * 64, target_identity="test",
        runtime=RuntimeFreeze(files={}, packages={}, python="test", configuration={}),
        inputs=PreparedInputs(competition_id=uuid4(), competition_season_id=uuid4(), season_year=2025,
            data_root=tmp_path, target_file=tmp_path / "target.json", model="scripted",
            steps=tuple(PreparedStep(week=week, snapshot_id=uuid4(), artifact_sha256="a" * 64,
                                    input_revision="b" * 64, editorial_cutoff_at=datetime(2025, 9, 9, tzinfo=UTC) + timedelta(weeks=week - 1)) for week in range(1, 4))))
    progress = CampaignProgress(campaign_hash=campaign_hash(campaign), steps=tuple(StepProgress() for _ in campaign.inputs.steps))
    write_json(tmp_path / "campaign.json", campaign.model_dump(mode="json"))
    save_progress(tmp_path, progress)
    backend = FakeBackend(campaign)
    controller = SeasonController(tmp_path, backend, verify_runtime=lambda _: None)
    return campaign, progress, backend, controller


@pytest.mark.asyncio
async def test_sequential_resume_and_noop_keep_exact_heads(setup):
    campaign, _, backend, controller = setup
    result = await controller.run(RunLimits(max_steps=1))
    assert result.state == "step_limit"
    head = backend.head()
    backend.noop = True
    assert (await controller.run(RunLimits(max_steps=1))).state == "step_limit"
    assert backend.head() == head
    backend.noop = False
    assert (await controller.run(RunLimits(max_steps=4))).state == "complete"
    assert backend.rows[campaign.generation_id(2, 1)].input_memory_revision_id == head
    assert (await controller.run(RunLimits(max_steps=4))).state == "complete"
    assert len(backend.calls) == 3


@pytest.mark.asyncio
async def test_failure_stops_and_explicit_retry_has_stable_new_identity(setup):
    campaign, _, backend, controller = setup
    backend.fail = True
    assert (await controller.run(RunLimits(max_steps=3))).state == "failed"
    assert backend.head() == campaign.root_revision_id
    assert (await controller.run(RunLimits(max_steps=3))).state == "failed"
    assert len(backend.calls) == 1
    backend.fail = False
    assert (await controller.run(RunLimits(max_steps=1, max_attempts_per_step=2), retry_failed=True)).state == "step_limit"
    assert backend.calls == [campaign.generation_id(0, 1), campaign.generation_id(0, 2)]


@pytest.mark.asyncio
async def test_crash_after_commit_before_export_reconciles_without_double_submit(setup):
    _, _, backend, controller = setup
    attempts = []
    def broken_export(*args):
        attempts.append(len(backend.calls))
        raise OSError("disk full")
    controller.export = broken_export
    with pytest.raises(OSError): await controller.run(RunLimits(max_steps=3))
    assert len(backend.calls) == 1
    with pytest.raises(OSError): await controller.run(RunLimits(max_steps=3))
    assert attempts == [1, 1]
    assert len(backend.calls) == 1
    controller.export = lambda *args: None
    assert (await controller.run(RunLimits(max_steps=3))).state == "complete"
    assert len(backend.calls) == 3


@pytest.mark.asyncio
async def test_pending_submission_resumes_but_running_never_reexecutes(setup):
    from backend.season_simulation.controller import step_request
    campaign, _, backend, controller = setup
    request = step_request(campaign, 0, 1, campaign.root_revision_id)
    backend.submit(request)
    row = backend.rows[request.generation_id]
    backend.rows[row.id] = row.model_copy(update={"status": GenerationStatus.RUNNING})
    assert (await controller.run(RunLimits())).state == "uncertain"
    assert backend.calls == []
    backend.rows[row.id] = row
    assert (await controller.run(RunLimits())).state == "step_limit"
    assert backend.calls == [row.id]


@pytest.mark.asyncio
async def test_stop_missing_inputs_and_budget_prevent_submission(setup):
    _, _, backend, controller = setup
    (controller.directory / "STOP").touch()
    assert (await controller.run(RunLimits())).state == "stopped"
    (controller.directory / "STOP").unlink()
    backend.tokens = 100
    assert (await controller.run(RunLimits(max_total_tokens=100))).state == "token_limit"
    backend.usage_complete = False
    assert (await controller.run(RunLimits(max_cost=1))).state == "usage_unavailable"
    backend.missing = True
    with pytest.raises(ValueError, match="missing"): await controller.run(RunLimits())
    assert backend.rows == {}


@pytest.mark.asyncio
async def test_wrong_persisted_intent_or_unrelated_memory_fails_closed(setup):
    _, _, backend, controller = setup
    await controller.run(RunLimits())
    gid = backend.calls[0]
    row = backend.rows[gid]
    backend.rows[gid] = row.model_copy(update={"week_end": 18})
    with pytest.raises(ValueError, match="intent"): controller.preflight()
    backend.rows[gid] = row
    backend.history.append(backend.history[-1].model_copy(update={"revision_id": uuid4(), "producing_generation_id": uuid4(), "sequence_number": 2}))
    with pytest.raises(ValueError, match="unrelated"): controller.preflight()


def test_config_tampering_and_reversed_weeks_rejected(setup):
    campaign, _, _, controller = setup
    value = campaign.model_dump(mode="json")
    value["inputs"]["model"] = "changed-model"
    write_json(controller.directory / "campaign.json", value)
    with pytest.raises(ValueError, match="freeze changed"): load_campaign(controller.directory)
    value["inputs"]["steps"][1]["week"] = 18
    with pytest.raises(ValueError, match="increasing"): Campaign.model_validate(value)


@pytest.mark.parametrize("weeks", [(1, 1, 3), (2, 1, 3)])
def test_duplicate_or_reversed_selected_weeks_rejected(setup, weeks):
    campaign, _, _, _ = setup
    value = campaign.model_dump(mode="json")
    for step, week in zip(value["inputs"]["steps"], weeks):
        step["week"] = week
    with pytest.raises(ValueError, match="increasing"):
        Campaign.model_validate(value)


@pytest.mark.asyncio
async def test_sparse_chronological_steps_only_commit_selected_weeks(setup):
    campaign, progress, backend, controller = setup
    value = campaign.model_dump(mode="json")
    for step, week in zip(value["inputs"]["steps"], (1, 2, 15)):
        step["week"] = week
        step["editorial_cutoff_at"] = (datetime(2025, 9, 9, tzinfo=UTC) + timedelta(weeks=week - 1)).isoformat()
    sparse = Campaign.model_validate(value)
    write_json(controller.directory / "campaign.json", sparse.model_dump(mode="json"))
    save_progress(controller.directory, progress.model_copy(update={"campaign_hash": campaign_hash(sparse)}))
    assert (await controller.run(RunLimits(max_steps=3))).state == "complete"
    assert [backend.rows[gid].week_end for gid in backend.calls] == [1, 2, 15]
    assert [revision.week for revision in backend.history[1:]] == [1, 2, 15]
    assert backend.rows[backend.calls[2]].input_memory_revision_id == backend.history[2].revision_id


@pytest.mark.asyncio
async def test_hard_interruption_after_commit_exports_before_next_submission(setup):
    _, _, backend, controller = setup
    execute = backend.execute
    class Crash(BaseException): pass
    async def interrupted(gid):
        await execute(gid)
        raise Crash()
    backend.execute = interrupted
    with pytest.raises(Crash): await controller.run(RunLimits(max_steps=3))
    assert load_campaign(controller.directory)[1].state == "running"
    backend.execute = execute
    def failed_export(*args): raise OSError("disk full during recovery")
    controller.export = failed_export
    with pytest.raises(OSError): await controller.run(RunLimits(max_steps=3))
    assert len(backend.calls) == 1
    controller.export = lambda *args: None
    assert (await controller.run(RunLimits(max_steps=3))).state == "complete"
    assert len(backend.calls) == 3


@pytest.mark.asyncio
async def test_initial_export_pending_blocks_execution_until_repaired(setup):
    _, progress, backend, controller = setup
    save_progress(controller.directory, progress.model_copy(update={"state": "export_pending"}))
    def failed_export(*args): raise OSError("initial dump failed")
    controller.export = failed_export
    with pytest.raises(OSError): await controller.run(RunLimits(max_steps=3))
    assert backend.calls == []
