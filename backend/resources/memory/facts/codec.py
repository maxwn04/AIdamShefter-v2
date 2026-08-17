"""Stored-schema codecs for fact versions."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.sql import Select

from backend.database.models.memory import FactVersion, MemoryItem, MemoryVersion
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.facts.objects import Fact, FactContent
from backend.resources.memory.revisions.hashing import StoredSchemaContent


def fact_rows_statement() -> Select[tuple[MemoryItem, MemoryVersion, FactVersion]]:
    """Select complete fact aggregates without exposing their storage joins."""

    return (
        sa.select(MemoryItem, MemoryVersion, FactVersion)
        .join(MemoryVersion, MemoryVersion.item_id == MemoryItem.id)
        .join(FactVersion, FactVersion.version_id == MemoryVersion.id)
        .where(MemoryItem.kind == MemoryKind.FACT.value)
    )


def decode_fact(
    item: MemoryItem,
    version: MemoryVersion,
    stored: FactVersion,
) -> Fact:
    content = _decode_content(version.content_schema_version, stored)
    return Fact.model_validate(
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


def encode_fact(
    content: FactContent,
    receipt_generation_id: UUID | None,
) -> dict[str, Any]:
    """Translate complete typed content into the current stored v1 row."""

    return {
        "claim": content.claim,
        "category": content.category,
        "structured_numbers": content.numbers,
        "confidence": content.confidence.value,
        "subjects": [subject.model_dump(mode="json") for subject in content.subjects],
        "originating_event_version_ids": list(
            content.originating_event_version_ids
        ),
        "primary_tool_call_id": content.primary_tool_call_id,
        "primary_tool_call_generation_id": receipt_generation_id,
        "primary_api_request_id": content.primary_api_request_id,
        "additional_source_hints": content.source_hints,
        "status": content.status.value,
    }


def stored_fact_content(content: FactContent) -> StoredSchemaContent:
    """Encode exact retained v1 logical content for canonical state hashing."""

    if content.schema_version != 1:
        raise ValueError(
            f"unsupported fact content schema version {content.schema_version}"
        )
    return StoredSchemaContent(
        memory_kind=MemoryKind.FACT,
        schema_version=1,
        payload={
            "schema_version": 1,
            "claim": content.claim,
            "category": content.category,
            "numbers": content.numbers,
            "confidence": content.confidence.value,
            "primary_tool_call_id": content.primary_tool_call_id,
            "primary_api_request_id": content.primary_api_request_id,
            "source_hints": content.source_hints,
            "status": content.status.value,
            "subjects": [
                {
                    "kind": subject.kind,
                    "id": subject.id,
                    "role": subject.role.value,
                    "display_name": subject.display_name,
                }
                for subject in content.subjects
            ],
            "originating_event_version_ids": list(
                content.originating_event_version_ids
            ),
        },
    )


def _decode_content(schema_version: int, stored: FactVersion) -> FactContent:
    if schema_version != 1:
        raise ValueError(f"unsupported fact content schema version {schema_version}")
    return FactContent.model_validate(
        {
            "schema_version": 1,
            "claim": stored.claim,
            "category": stored.category,
            "numbers": stored.structured_numbers or {},
            "confidence": stored.confidence,
            "status": stored.status,
            "subjects": stored.subjects,
            "originating_event_version_ids": stored.originating_event_version_ids,
            "primary_tool_call_id": stored.primary_tool_call_id,
            "primary_api_request_id": stored.primary_api_request_id,
            "source_hints": stored.additional_source_hints,
        }
    )
