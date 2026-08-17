"""Stored-schema codecs for trigger versions."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.sql import Select

from backend.database.models.memory import MemoryItem, MemoryVersion, TriggerVersion
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.revisions.hashing import StoredSchemaContent
from backend.resources.memory.triggers.objects import Trigger, TriggerContent


def trigger_rows_statement(
) -> Select[tuple[MemoryItem, MemoryVersion, TriggerVersion]]:
    """Select complete trigger aggregates without exposing storage joins."""

    return (
        sa.select(MemoryItem, MemoryVersion, TriggerVersion)
        .join(MemoryVersion, MemoryVersion.item_id == MemoryItem.id)
        .join(TriggerVersion, TriggerVersion.version_id == MemoryVersion.id)
        .where(MemoryItem.kind == MemoryKind.TRIGGER.value)
    )


def decode_trigger(
    item: MemoryItem,
    version: MemoryVersion,
    stored: TriggerVersion,
) -> Trigger:
    content = _decode_content(version.content_schema_version, stored)
    return Trigger.model_validate(
        {
            "item": {
                "item_id": item.id,
                "competition_id": item.competition_id,
                "kind": item.kind,
                "agent_key": item.agent_key,
                "created_at": item.created_at,
            },
            "version": {
                "version_id": version.id,
                "revision_number": version.revision_number,
                "content_schema_version": version.content_schema_version,
                "introduced_revision_id": version.introduced_revision_id,
                "retired_revision_id": version.retired_revision_id,
                "competition_season_id": version.competition_season_id,
                "week": version.week,
                "occurred_at": version.occurred_at,
                "creating_generation_id": version.creating_generation_id,
                "creating_tool_call_id": version.creating_tool_call_id,
                "change_reason": version.change_reason,
                "recorded_at": version.recorded_at,
            },
            "content": content,
        }
    )


def encode_trigger(content: TriggerContent) -> dict[str, Any]:
    """Translate complete typed content into the current stored v1 row."""

    return {
        "trigger_type": content.trigger_type.value,
        "status": content.status.value,
        "fire_policy": content.fire_policy.value,
        "target_competition_season_id": content.target_competition_season_id,
        "target_storyline_item_id": content.target_storyline_item_id,
        "origin_event_item_id": content.origin_event_item_id,
        "target_week": content.target_week,
        "target_at": content.target_at,
        "condition": content.condition.model_dump(mode="json"),
        "resolution_reason": content.resolution_reason,
    }


def stored_trigger_content(content: TriggerContent) -> StoredSchemaContent:
    """Encode exact retained v1 logical content for canonical state hashing."""

    if content.schema_version != 1:
        raise ValueError(
            f"unsupported trigger content schema version {content.schema_version}"
        )
    return StoredSchemaContent(
        memory_kind=MemoryKind.TRIGGER,
        schema_version=1,
        payload={
            "schema_version": 1,
            "trigger_type": content.trigger_type.value,
            "status": content.status.value,
            "fire_policy": content.fire_policy.value,
            "target_competition_season_id": content.target_competition_season_id,
            "target_storyline_item_id": content.target_storyline_item_id,
            "origin_event_item_id": content.origin_event_item_id,
            "target_week": content.target_week,
            "target_at": content.target_at,
            "condition": content.condition.model_dump(mode="python"),
            "resolution_reason": content.resolution_reason,
        },
    )


def _decode_content(schema_version: int, stored: TriggerVersion) -> TriggerContent:
    if schema_version != 1:
        raise ValueError(
            f"unsupported trigger content schema version {schema_version}"
        )
    return TriggerContent.model_validate(
        {
            "schema_version": 1,
            "trigger_type": stored.trigger_type,
            "status": stored.status,
            "fire_policy": stored.fire_policy,
            "target_competition_season_id": stored.target_competition_season_id,
            "target_storyline_item_id": stored.target_storyline_item_id,
            "origin_event_item_id": stored.origin_event_item_id,
            "target_week": stored.target_week,
            "target_at": stored.target_at,
            "condition": stored.condition,
            "resolution_reason": stored.resolution_reason,
        }
    )
