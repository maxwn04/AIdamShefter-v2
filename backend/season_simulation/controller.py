"""Serial execution and restart reconciliation over normal generations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import time
from typing import ContextManager, Protocol
from uuid import UUID

from backend.resources.memory.revisions import CanonicalRevision
from backend.resources.reporting.generations import Generation, GenerationKind, GenerationStatus
from backend.season_simulation.contracts import Campaign, CampaignProgress, RunLimits, StepProgress
from backend.season_simulation.freeze import assert_runtime
from backend.season_simulation.store import load_campaign, save_progress
from backend.services.generations import GenerationRequest, PreparedGenerationExecution
from backend.services.generations.service import _resolved_settings


class CampaignBackend(Protocol):
    def lock(self) -> ContextManager[None]: ...
    def generations(self) -> tuple[Generation, ...]: ...
    def revisions(self) -> tuple[CanonicalRevision, ...]: ...
    def head(self) -> UUID: ...
    def validate_inputs(self, campaign: Campaign) -> None: ...
    def submit(self, request: GenerationRequest) -> None: ...
    async def execute(self, generation_id: UUID) -> None: ...
    def usage(self, generation_ids: tuple[UUID, ...]) -> tuple[int, Decimal, bool]: ...


@dataclass(frozen=True)
class Reconciled:
    next_step: int
    head: UUID
    latest: Generation | None
    generation_ids: tuple[UUID, ...]


def step_request(campaign: Campaign, index: int, attempt: int, head: UUID) -> GenerationRequest:
    step = campaign.inputs.steps[index]
    settings = campaign.inputs.settings.model_copy(update={
        "prepared_execution": PreparedGenerationExecution(
            data_snapshot_id=step.snapshot_id, artifact_sha256=step.artifact_sha256,
            input_revision=step.input_revision, expected_memory_revision_id=head,
            editorial_cutoff_at=step.editorial_cutoff_at,
        ),
    })
    return GenerationRequest(
        generation_id=campaign.generation_id(index, attempt),
        competition_id=campaign.inputs.competition_id,
        competition_season_id=campaign.inputs.competition_season_id,
        kind=GenerationKind.LIVE, request_text=campaign.inputs.request_template.format(week=step.week),
        week_start=step.week, week_end=step.week,
        requested_primary_model=campaign.inputs.model, settings=settings,
        rerun_of_generation_id=campaign.generation_id(index, attempt - 1) if attempt > 1 else None,
    )


def _verify_generation(row: Generation, request: GenerationRequest) -> None:
    fields = ("competition_id", "competition_season_id", "kind", "request_text", "week_start",
              "week_end", "requested_primary_model", "rerun_of_generation_id")
    if any(getattr(row, field) != getattr(request, field) for field in fields):
        raise ValueError("persisted generation intent differs from campaign")
    if row.settings != _resolved_settings(request.settings):
        raise ValueError("persisted generation settings differ from campaign")
    if row.input_memory_revision_id not in (None, request.settings.prepared_execution.expected_memory_revision_id):
        raise ValueError("generation consumed the wrong canonical memory revision")
    if row.data_snapshot_id not in (None, request.settings.prepared_execution.data_snapshot_id):
        raise ValueError("generation consumed the wrong prepared snapshot")


def reconcile(campaign: Campaign, progress: CampaignProgress, backend: CampaignBackend) -> Reconciled:
    rows = {row.id: row for row in backend.generations()}
    revisions = backend.revisions()
    roots = [revision for revision in revisions if revision.sequence_number == 0]
    if len(roots) != 1 or roots[0].revision_id != campaign.root_revision_id or roots[0].state_content_hash != campaign.root_state_hash:
        raise ValueError("database source-only root differs from campaign")
    produced = {revision.producing_generation_id: revision for revision in revisions if revision.sequence_number > 0}
    expected_ids = {campaign.generation_id(i, attempt) for i, step in enumerate(progress.steps)
                    for attempt in range(1, step.attempts + 1)}
    if rows.keys() - expected_ids:
        raise ValueError("database contains generations outside this campaign")
    head = campaign.root_revision_id
    used_revisions = {head}
    next_step = len(progress.steps)
    latest: Generation | None = None
    for index, step in enumerate(progress.steps):
        succeeded = False
        for attempt in range(1, step.attempts + 1):
            gid = campaign.generation_id(index, attempt)
            row = rows.get(gid)
            if index > next_step and row is not None:
                raise ValueError("a later generation exists before its predecessor succeeded")
            if row is None:
                if attempt != step.attempts:
                    raise ValueError("missing previously attempted generation")
                continue
            _verify_generation(row, step_request(campaign, index, attempt, head))
            if row.status is GenerationStatus.SUCCEEDED:
                if attempt != step.attempts or row.input_memory_revision_id != head or row.data_snapshot_id is None:
                    raise ValueError("successful step has inconsistent attempts or input head")
                revision = produced.get(gid)
                if revision is not None:
                    if revision.previous_revision_id != head:
                        raise ValueError("successful memory revision is not the expected successor")
                    head = revision.revision_id
                    used_revisions.add(head)
                succeeded = True
            elif gid in produced:
                raise ValueError("unsuccessful generation advanced canonical memory")
            elif attempt < step.attempts and row.status not in (GenerationStatus.FAILED, GenerationStatus.CANCELLED):
                raise ValueError("retry intent exists for a nonterminal generation")
            if attempt == step.attempts and index <= next_step:
                latest = row
        if not succeeded and next_step == len(progress.steps):
            next_step = index
            latest = rows.get(campaign.generation_id(index, step.attempts))
    if {revision.revision_id for revision in revisions} != used_revisions or backend.head() != head:
        raise ValueError("canonical memory contains unrelated or inconsistent writes")
    return Reconciled(next_step, head, latest, tuple(sorted(rows, key=str)))


class SeasonController:
    def __init__(self, directory: Path, backend: CampaignBackend, *,
                 verify_runtime: Callable = assert_runtime,
                 export: Callable[[Campaign, CampaignProgress], None] | None = None) -> None:
        self.directory = directory
        self.backend = backend
        self.verify_runtime = verify_runtime
        self.export = export

    def preflight(self) -> Reconciled:
        campaign, progress = load_campaign(self.directory)
        self.verify_runtime(campaign.runtime)
        self.backend.validate_inputs(campaign)
        return reconcile(campaign, progress, self.backend)

    async def run(self, limits: RunLimits, *, retry_failed: bool = False) -> CampaignProgress:
        started = time.monotonic()
        executed = 0
        with self.backend.lock():
            campaign, progress = load_campaign(self.directory)
            if progress.state in {"running", "export_pending", "export_failed"}:
                # `running` also covers process death after DB success but before
                # export starts, where no exception handler could journal failure.
                self.preflight()
                self._export(campaign, progress)
                progress = progress.model_copy(update={"state": "resumed", "detail": None})
                save_progress(self.directory, progress)
            while True:
                # Check runtime and *every* prepared input before any possible provider work.
                state = self.preflight()
                reason = None
                if state.next_step == len(campaign.inputs.steps):
                    reason = "complete"
                elif state.latest is not None and state.latest.status is GenerationStatus.RUNNING:
                    return self._stop(progress, "uncertain", "Generation is running; inspect it before explicit recovery.", campaign)
                elif state.latest is not None and state.latest.status in (GenerationStatus.FAILED, GenerationStatus.CANCELLED) and not retry_failed:
                    return self._stop(progress, "failed", state.latest.failure_summary, campaign)
                elif (self.directory / "STOP").exists():
                    reason = "stopped"
                elif executed >= limits.max_steps:
                    reason = "step_limit"
                elif limits.max_seconds is not None and time.monotonic() - started >= limits.max_seconds:
                    reason = "time_limit"
                if reason is None and (limits.max_total_tokens is not None or limits.max_cost is not None):
                    tokens, cost, complete = self.backend.usage(state.generation_ids)
                    if not complete:
                        reason = "usage_unavailable"
                    elif limits.max_total_tokens is not None and tokens >= limits.max_total_tokens:
                        reason = "token_limit"
                    elif limits.max_cost is not None and cost >= Decimal(str(limits.max_cost)):
                        reason = "cost_limit"
                if reason is not None:
                    progress = progress.model_copy(update={"state": reason, "detail": None})
                    save_progress(self.directory, progress)
                    self._export(campaign, progress)
                    return progress
                index = state.next_step
                attempt = progress.steps[index].attempts
                if state.latest is not None:
                    if state.latest.status is GenerationStatus.RUNNING:
                        return self._stop(progress, "uncertain", "Generation is running; inspect it before explicit recovery.", campaign)
                    if state.latest.status in (GenerationStatus.FAILED, GenerationStatus.CANCELLED):
                        if not retry_failed or attempt >= limits.max_attempts_per_step:
                            return self._stop(progress, "failed", state.latest.failure_summary, campaign)
                        attempts = list(progress.steps)
                        attempts[index] = StepProgress(attempts=attempt + 1)
                        progress = progress.model_copy(update={"steps": tuple(attempts)})
                        # Intent first: crash before/after submit is reconciled by the same UUID.
                        save_progress(self.directory, progress)
                        attempt += 1
                request = step_request(campaign, index, attempt, state.head)
                if state.latest is None or state.latest.id != request.generation_id:
                    self.backend.submit(request)
                progress = progress.model_copy(update={"state": "running", "detail": str(request.generation_id)})
                save_progress(self.directory, progress)
                await self.backend.execute(request.generation_id)
                executed += 1
                # Export each completed boundary before proceeding; failure is retryable
                # without another generation because reconciliation reads durable success.
                reconcile(campaign, progress, self.backend)
                self._export(campaign, progress)

    def _stop(self, progress: CampaignProgress, state: str, detail: str | None, campaign: Campaign) -> CampaignProgress:
        progress = progress.model_copy(update={"state": state, "detail": detail})
        save_progress(self.directory, progress)
        self._export(campaign, progress)
        return progress

    def _export(self, campaign: Campaign, progress: CampaignProgress) -> None:
        if self.export is not None:
            try:
                self.export(campaign, progress)
            except Exception as exc:
                save_progress(self.directory, progress.model_copy(update={"state": "export_failed", "detail": str(exc)}))
                raise
