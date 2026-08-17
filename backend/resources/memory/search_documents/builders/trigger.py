from __future__ import annotations

import hashlib
import json
from typing import Any, Final, cast
from uuid import UUID

from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.search_documents.objects import (
    SearchDocumentProjection,
)
from backend.resources.memory.triggers.conditions.rematch import RematchCondition
from backend.resources.memory.triggers.objects import TriggerContent


TRIGGER_DOCUMENT_BUILDER_VERSION: Final = 1


def build_trigger_document(content: TriggerContent) -> SearchDocumentProjection:
    """Deterministically flatten complete trigger content for discovery."""

    entity_keys = tuple(sorted(_entity_keys(content)))
    related_item_ids = tuple(sorted(_related_item_ids(content), key=str))
    text_parts = [
        f"trigger type: {content.trigger_type.value}",
        f"status: {content.status.value}",
        f"fire policy: {content.fire_policy.value}",
        *_target_text(content),
        *_condition_text(content),
    ]
    if content.resolution_reason is not None:
        text_parts.append(f"resolution: {content.resolution_reason}")

    return SearchDocumentProjection(
        kind=MemoryKind.TRIGGER,
        status=content.status.value,
        entity_keys=entity_keys,
        related_item_ids=related_item_ids,
        document_text="\n".join(text_parts),
        builder_version=TRIGGER_DOCUMENT_BUILDER_VERSION,
        content_hash=_trigger_content_hash(content),
    )


def _entity_keys(content: TriggerContent) -> set[str]:
    keys: set[str] = set()
    if content.target_competition_season_id is not None:
        keys.add(f"season:{content.target_competition_season_id}")
    if isinstance(content.condition, RematchCondition):
        keys.update(
            f"franchise:{franchise_id}"
            for franchise_id in content.condition.franchise_ids
        )
    return keys


def _related_item_ids(content: TriggerContent) -> set[UUID]:
    return {
        item_id
        for item_id in (
            content.target_storyline_item_id,
            content.origin_event_item_id,
        )
        if item_id is not None
    }


def _target_text(content: TriggerContent) -> list[str]:
    parts: list[str] = []
    if content.target_competition_season_id is not None:
        parts.append(f"target season: {content.target_competition_season_id}")
    if content.target_storyline_item_id is not None:
        parts.append(f"target storyline: {content.target_storyline_item_id}")
    if content.origin_event_item_id is not None:
        parts.append(f"origin event: {content.origin_event_item_id}")
    if content.target_week is not None:
        parts.append(f"target week: {content.target_week}")
    if content.target_at is not None:
        parts.append(f"target time: {content.target_at.isoformat()}")
    return parts


def _condition_text(content: TriggerContent) -> list[str]:
    if isinstance(content.condition, RematchCondition):
        franchises = sorted(str(value) for value in content.condition.franchise_ids)
        return [f"rematch franchises: {' '.join(franchises)}"]
    return ["condition: trade evaluation"]


def _trigger_content_hash(content: TriggerContent) -> str:
    serialized = _canonical_json(_canonical_trigger_content(content)).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _canonical_trigger_content(content: TriggerContent) -> dict[str, Any]:
    dumped = cast(dict[str, Any], content.model_dump(mode="json"))
    condition = cast(dict[str, Any], dumped["condition"])
    if condition["kind"] == "rematch":
        franchise_ids = cast(list[str], condition["franchise_ids"])
        condition["franchise_ids"] = sorted(franchise_ids)
    return {
        "memory_kind": content.memory_kind.value,
        "content": dumped,
    }


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
