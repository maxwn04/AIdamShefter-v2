"""Stored-schema codecs for event versions."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.sql import Select

from backend.database.models.memory import EventVersion, MemoryItem, MemoryVersion
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.events.objects import Event, EventContent
from backend.resources.memory.revisions.hashing import StoredSchemaContent


def event_rows_statement() -> Select[tuple[MemoryItem, MemoryVersion, EventVersion]]:
    """Select complete event aggregates without exposing their storage joins."""

    return (
        sa.select(MemoryItem, MemoryVersion, EventVersion)
        .join(MemoryVersion, MemoryVersion.item_id == MemoryItem.id)
        .join(EventVersion, EventVersion.version_id == MemoryVersion.id)
        .where(MemoryItem.kind == MemoryKind.EVENT.value)
    )


def decode_event(
    item: MemoryItem,
    version: MemoryVersion,
    stored: EventVersion,
) -> Event:
    content = _decode_content(version.content_schema_version, stored)
    return Event.model_validate(
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


def encode_event(
    content: EventContent,
    receipt_generation_id: UUID | None,
) -> dict[str, Any]:
    """Translate complete typed content into the current stored v1 row."""

    return {
        "event_type": content.event_type.value,
        "headline": content.headline,
        "summary": content.summary,
        "salience": content.salience,
        "confidence": content.confidence.value,
        "status": content.status.value,
        "details": content.details.model_dump(mode="json"),
        "additional_source_hints": content.source_hints,
        "primary_tool_call_id": content.primary_tool_call_id,
        "primary_tool_call_generation_id": receipt_generation_id,
        "primary_api_request_id": content.primary_api_request_id,
    }


def stored_event_content(content: EventContent) -> StoredSchemaContent:
    """Encode exact retained v1 logical content for canonical state hashing."""

    if content.schema_version != 1:
        raise ValueError(
            f"unsupported event content schema version {content.schema_version}"
        )
    return StoredSchemaContent(
        memory_kind=MemoryKind.EVENT,
        schema_version=1,
        payload={
            "schema_version": 1,
            "event_type": content.event_type.value,
            "headline": content.headline,
            "summary": content.summary,
            "salience": content.salience,
            "confidence": content.confidence.value,
            "status": content.status.value,
            "details": content.details.model_dump(mode="python"),
            "primary_tool_call_id": content.primary_tool_call_id,
            "primary_api_request_id": content.primary_api_request_id,
            "source_hints": content.source_hints,
        },
    )


def _decode_content(schema_version: int, stored: EventVersion) -> EventContent:
    if schema_version != 1:
        raise ValueError(f"unsupported event content schema version {schema_version}")
    return EventContent.model_validate(
        {
            "schema_version": 1,
            "event_type": stored.event_type,
            "headline": stored.headline,
            "summary": stored.summary,
            "salience": stored.salience,
            "confidence": stored.confidence,
            "status": stored.status,
            "details": stored.details,
            "primary_tool_call_id": stored.primary_tool_call_id,
            "primary_api_request_id": stored.primary_api_request_id,
            "source_hints": stored.additional_source_hints,
        }
    )
