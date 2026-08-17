"""Stored-schema codecs for storyline versions."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.sql import Select

from backend.database.models.memory import MemoryItem, MemoryVersion, StorylineVersion
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.revisions.hashing import StoredSchemaContent
from backend.resources.memory.storylines.objects import Storyline, StorylineContent


def storyline_rows_statement(
) -> Select[tuple[MemoryItem, MemoryVersion, StorylineVersion]]:
    """Select complete storyline aggregates without exposing storage joins."""

    return (
        sa.select(MemoryItem, MemoryVersion, StorylineVersion)
        .join(MemoryVersion, MemoryVersion.item_id == MemoryItem.id)
        .join(StorylineVersion, StorylineVersion.version_id == MemoryVersion.id)
        .where(MemoryItem.kind == MemoryKind.STORYLINE.value)
    )


def decode_storyline(
    item: MemoryItem,
    version: MemoryVersion,
    stored: StorylineVersion,
) -> Storyline:
    content = _decode_content(version.content_schema_version, stored)
    return Storyline.model_validate(
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


def encode_storyline(content: StorylineContent) -> dict[str, Any]:
    """Translate complete typed content into the current stored v1 row."""

    return {
        "headline": content.headline,
        "summary": content.summary,
        "status": content.status.value,
        "arc_type": content.arc_type,
        "salience": content.salience,
        "tags": list(content.tags),
        "subjects": [subject.model_dump(mode="json") for subject in content.subjects],
        "evidence": [reference.model_dump(mode="json") for reference in content.evidence],
        "related_storylines": [
            reference.model_dump(mode="json")
            for reference in content.related_storylines
        ],
        "callback_condition": content.callback_condition,
        "resolution_summary": content.resolution_summary,
    }


def stored_storyline_content(content: StorylineContent) -> StoredSchemaContent:
    """Encode exact retained v1 logical content for canonical state hashing."""

    if content.schema_version != 1:
        raise ValueError(
            f"unsupported storyline content schema version {content.schema_version}"
        )
    return StoredSchemaContent(
        memory_kind=MemoryKind.STORYLINE,
        schema_version=1,
        payload={
            "schema_version": 1,
            "headline": content.headline,
            "summary": content.summary,
            "status": content.status.value,
            "arc_type": content.arc_type,
            "salience": content.salience,
            "tags": list(content.tags),
            "subjects": [
                {
                    "kind": subject.kind,
                    "id": subject.id,
                    "role": subject.role.value,
                    "display_name": subject.display_name,
                }
                for subject in content.subjects
            ],
            "evidence": [
                {
                    "kind": reference.kind,
                    "version_id": reference.version_id,
                    "role": reference.role.value,
                }
                for reference in content.evidence
            ],
            "related_storylines": [
                {
                    "item_id": reference.item_id,
                    "role": reference.role.value,
                }
                for reference in content.related_storylines
            ],
            "callback_condition": content.callback_condition,
            "resolution_summary": content.resolution_summary,
        },
    )


def _decode_content(
    schema_version: int,
    stored: StorylineVersion,
) -> StorylineContent:
    if schema_version != 1:
        raise ValueError(
            f"unsupported storyline content schema version {schema_version}"
        )
    return StorylineContent.model_validate(
        {
            "schema_version": 1,
            "headline": stored.headline,
            "summary": stored.summary,
            "status": stored.status,
            "arc_type": stored.arc_type,
            "salience": stored.salience,
            "tags": stored.tags,
            "subjects": stored.subjects,
            "evidence": stored.evidence,
            "related_storylines": stored.related_storylines,
            "callback_condition": stored.callback_condition,
            "resolution_summary": stored.resolution_summary,
        }
    )
