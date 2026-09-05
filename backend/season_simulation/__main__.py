"""Local operator commands. Only `run` can call the reporter/provider."""

import argparse
import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import os
from uuid import uuid4

from sqlalchemy import create_engine

from backend.season_simulation.backend import DatabaseCampaignBackend
from backend.season_simulation.contracts import Campaign, CampaignProgress, PreparedInputs, RunLimits, StepProgress
from backend.season_simulation.controller import SeasonController
from backend.season_simulation.docker import DockerTarget, read_target, target_environment, verify_target
from backend.season_simulation.export import export_campaign, verify_export
from backend.season_simulation.freeze import archive_runtime, runtime_freeze
from backend.season_simulation.store import campaign_hash, load_campaign, save_progress, write_json


@contextmanager
def open_backend(inputs: PreparedInputs, expected_identity: str | None = None) -> Iterator[tuple[DatabaseCampaignBackend, DockerTarget]]:
    target = read_target(inputs.target_file)
    verify_target(target)
    if expected_identity is not None and target.identity != expected_identity:
        raise ValueError("campaign target was replaced")
    environment = target_environment(target)
    environment["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    # Provider libraries must not implicitly import another checkout's .env at
    # first completion. Credentials are supplied explicitly by the operator.
    environment["PYTHON_DOTENV_DISABLED"] = "1"
    if Path(environment["AIDAM_DATALAYER_ROOT"]).resolve() != inputs.data_root.resolve():
        raise ValueError("prepared input data root differs from target")
    previous = {key: os.environ.get(key) for key in environment}
    os.environ.update(environment)
    engine = create_engine(environment["AIDAM_WORKER_DATABASE_URL"], pool_size=3, max_overflow=2)
    backend = None
    try:
        backend = DatabaseCampaignBackend(engine, inputs.competition_id)
        yield backend, target
    finally:
        if backend is not None:
            backend.close()
        engine.dispose()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def initialize(prepared: Path, directory: Path) -> Campaign:
    inputs = PreparedInputs.model_validate_json(prepared.read_text(encoding="utf-8"))
    directory = directory.resolve()
    if ".context" not in directory.parts:
        raise ValueError("campaign directory must live under ignored .context")
    if directory.exists():
        raise FileExistsError("refusing to overwrite an existing campaign directory")
    with open_backend(inputs) as (backend, target), backend.lock():
        if backend.generations():
            raise ValueError("campaign initialization requires source-only state with no generations")
        root = backend.revision_manager.ensure_current()
        if root.sequence_number != 0 or len(backend.revisions()) != 1:
            raise ValueError("campaign initialization requires empty canonical memory")
        campaign = Campaign(
            campaign_id=uuid4(), inputs=inputs, root_revision_id=root.revision_id,
            root_state_hash=root.state_content_hash, target_identity=target.identity,
            runtime=runtime_freeze(),
        )
        backend.validate_inputs(campaign)
        directory.mkdir(parents=True)
        archive_runtime(campaign.runtime, directory / "runtime")
        write_json(directory / "campaign.json", campaign.model_dump(mode="json"))
        progress = CampaignProgress(campaign_hash=campaign_hash(campaign), steps=tuple(StepProgress() for _ in inputs.steps), state="export_pending")
        save_progress(directory, progress)
        try:
            export_campaign(directory, campaign, progress, backend.engine, target)
        except Exception as exc:
            save_progress(directory, progress.model_copy(update={"state": "export_failed", "detail": str(exc)}))
            raise
        save_progress(directory, progress.model_copy(update={"state": "prepared"}))
        return campaign


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Freeze a prepared source-only campaign; no model calls")
    init.add_argument("--prepared", type=Path, required=True)
    init.add_argument("--campaign-dir", type=Path, required=True)
    for name in ("dry-run", "run", "export", "stop", "clear-stop"):
        command = commands.add_parser(name)
        command.add_argument("--campaign-dir", type=Path, required=True)
        if name == "run":
            command.add_argument("--max-steps", type=int, default=1)
            command.add_argument("--max-attempts-per-step", type=int, default=1)
            command.add_argument("--max-total-tokens", type=int)
            command.add_argument("--max-cost", type=float)
            command.add_argument("--max-seconds", type=float)
            command.add_argument("--retry-failed", action="store_true")
    verify = commands.add_parser("verify-export", help="Verify an offline export with no database")
    verify.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.command == "init":
        campaign = initialize(args.prepared, args.campaign_dir)
        print(f"Prepared campaign {campaign.campaign_id}; no generation executed")
        return
    if args.command == "verify-export":
        verify_export(args.directory)
        print("Export verified")
        return
    campaign, progress = load_campaign(args.campaign_dir)
    if args.command in {"stop", "clear-stop"}:
        stop = args.campaign_dir / "STOP"
        if args.command == "stop":
            stop.write_text("Stop at next generation boundary.\n", encoding="utf-8")
        else:
            stop.unlink(missing_ok=True)
        print(args.command)
        return
    with open_backend(campaign.inputs, campaign.target_identity) as (backend, target):
        def export(campaign: Campaign, progress: CampaignProgress) -> Path:
            return export_campaign(args.campaign_dir, campaign, progress, backend.engine, target)
        controller = SeasonController(args.campaign_dir, backend, export=export)
        if args.command == "dry-run":
            with backend.lock():
                state = controller.preflight()
                print(f"Validated {len(campaign.inputs.steps)} prepared inputs; next step {state.next_step + 1}; no model calls")
        elif args.command == "export":
            with backend.lock():
                # Retention remains possible after runtime source changes. Export
                # uses archived assets and persisted rows, never executes code.
                print(export(campaign, progress))
        else:
            limits = RunLimits(**{name: getattr(args, name) for name in RunLimits.model_fields})
            result = asyncio.run(controller.run(limits, retry_failed=args.retry_failed))
            print(f"Campaign {result.state}: {result.detail or ''}")
            if result.state in {"failed", "uncertain", "usage_unavailable", "export_failed"}:
                raise SystemExit(2)


if __name__ == "__main__":
    main()
