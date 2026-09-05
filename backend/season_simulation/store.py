"""Atomic local intent journal, backed by durable generation reconciliation."""

import json
import os
from pathlib import Path
from uuid import uuid4

from backend.season_simulation.contracts import Campaign, CampaignProgress
from backend.services.generations.manifest import canonical_json_sha256


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def campaign_hash(campaign: Campaign) -> str:
    return canonical_json_sha256(campaign.model_dump(mode="json"))


def load_campaign(directory: Path) -> tuple[Campaign, CampaignProgress]:
    campaign = Campaign.model_validate_json((directory / "campaign.json").read_text(encoding="utf-8"))
    progress = CampaignProgress.model_validate_json((directory / "progress.json").read_text(encoding="utf-8"))
    if progress.campaign_hash != campaign_hash(campaign):
        raise ValueError("campaign config or input freeze changed")
    if len(progress.steps) != len(campaign.inputs.steps):
        raise ValueError("progress does not match campaign steps")
    return campaign, progress


def save_progress(directory: Path, progress: CampaignProgress) -> None:
    write_json(directory / "progress.json", progress.model_dump(mode="json"))
