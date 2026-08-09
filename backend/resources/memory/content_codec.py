"""Schema-version-aware conversion between typed memory content and ORM rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

from backend.database.models.memory import (
    ContextNoteVersion,
    EventVersion,
    FactVersion,
    StorylineVersion,
    TriggerVersion,
)
from backend.resources.memory.objects import (
    MemoryContent,
    MemoryKind,
    decode_memory_content,
)
from backend.resources.memory.errors import UnsupportedMemorySchema


@dataclass(frozen=True, slots=True)
class _ContentCodec:
    model: type[Any]
    encode: Callable[[UUID, UUID, UUID, Any], dict[str, Any]]
    decode: Callable[[Any], dict[str, Any]]


def typed_content_model(kind: MemoryKind) -> type[Any]:
    """Return the canonical typed table for one memory kind."""

    return _CODECS[(kind, 1)].model


def typed_content_models() -> tuple[type[Any], ...]:
    """Return the typed tables that own cross-kind status vocabulary."""

    return tuple(codec.model for codec in _CODECS.values())


def decode_stored_content(
    kind: MemoryKind,
    schema_version: int,
    row: Any,
) -> MemoryContent:
    """Decode one complete typed ORM row through the matching schema codec."""

    codec = _codec(kind, schema_version)
    return decode_memory_content(kind, schema_version, codec.decode(row))


def encode_stored_content(
    version_id: UUID,
    competition_id: UUID,
    generation_id: UUID,
    content: MemoryContent,
) -> Any:
    """Build one complete typed ORM row through the matching schema codec."""

    kind = MemoryKind(content.kind)
    codec = _codec(kind, content.schema_version)
    return codec.model(
        **codec.encode(version_id, competition_id, generation_id, content)
    )


def _codec(kind: MemoryKind, schema_version: int) -> _ContentCodec:
    try:
        return _CODECS[(kind, schema_version)]
    except KeyError as error:
        raise UnsupportedMemorySchema(
            f"unsupported stored memory schema: {kind.value} v{schema_version}"
        ) from error


def _encode_storyline(
    version_id: UUID,
    _competition_id: UUID,
    _generation_id: UUID,
    content: Any,
) -> dict[str, Any]:
    values = content.model_dump(mode="json")
    return {
        "version_id": version_id,
        "headline": content.headline,
        "summary": content.summary,
        "status": content.status.value,
        "arc_type": content.arc_type,
        "salience": content.salience,
        "tags": list(content.tags),
        "subjects": values["subjects"],
        "evidence": values["evidence"],
        "related_storylines": values["related_storylines"],
        "callback_condition": content.callback_condition,
        "resolution_summary": content.resolution_summary,
    }


def _decode_storyline(row: Any) -> dict[str, Any]:
    return {
        "headline": row.headline,
        "summary": row.summary,
        "status": row.status,
        "arc_type": row.arc_type,
        "salience": row.salience,
        "tags": row.tags,
        "subjects": row.subjects,
        "evidence": row.evidence,
        "related_storylines": row.related_storylines,
        "callback_condition": row.callback_condition,
        "resolution_summary": row.resolution_summary,
    }


def _encode_fact(
    version_id: UUID,
    competition_id: UUID,
    generation_id: UUID,
    content: Any,
) -> dict[str, Any]:
    values = content.model_dump(mode="json")
    return {
        "version_id": version_id,
        "competition_id": competition_id,
        "claim": content.claim,
        "category": content.category,
        "structured_numbers": values["numbers"],
        "confidence": content.confidence.value,
        "subjects": values["subjects"],
        "originating_event_version_ids": list(
            content.originating_event_version_ids
        ),
        "primary_tool_call_id": content.primary_tool_call_id,
        "primary_tool_call_generation_id": (
            generation_id if content.primary_tool_call_id is not None else None
        ),
        "primary_api_request_id": content.primary_api_request_id,
        "additional_source_hints": values["source_hints"],
        "status": content.status.value,
    }


def _decode_fact(row: Any) -> dict[str, Any]:
    return {
        "claim": row.claim,
        "category": row.category,
        "numbers": row.structured_numbers or {},
        "confidence": row.confidence,
        "status": row.status,
        "subjects": row.subjects,
        "originating_event_version_ids": row.originating_event_version_ids,
        "primary_tool_call_id": row.primary_tool_call_id,
        "primary_api_request_id": row.primary_api_request_id,
        "source_hints": row.additional_source_hints,
    }


def _encode_event(
    version_id: UUID,
    competition_id: UUID,
    generation_id: UUID,
    content: Any,
) -> dict[str, Any]:
    values = content.model_dump(mode="json")
    return {
        "version_id": version_id,
        "competition_id": competition_id,
        "event_type": content.event_type.value,
        "headline": content.headline,
        "summary": content.summary,
        "salience": content.salience,
        "confidence": content.confidence.value,
        "status": content.status.value,
        "details": values["details"],
        "additional_source_hints": values["source_hints"],
        "primary_tool_call_id": content.primary_tool_call_id,
        "primary_tool_call_generation_id": (
            generation_id if content.primary_tool_call_id is not None else None
        ),
        "primary_api_request_id": content.primary_api_request_id,
    }


def _decode_event(row: Any) -> dict[str, Any]:
    return {
        "event_type": row.event_type,
        "headline": row.headline,
        "summary": row.summary,
        "salience": row.salience,
        "confidence": row.confidence,
        "status": row.status,
        "details": row.details,
        "primary_tool_call_id": row.primary_tool_call_id,
        "primary_api_request_id": row.primary_api_request_id,
        "source_hints": row.additional_source_hints,
    }


def _encode_trigger(
    version_id: UUID,
    competition_id: UUID,
    _generation_id: UUID,
    content: Any,
) -> dict[str, Any]:
    values = content.model_dump(mode="json")
    return {
        "version_id": version_id,
        "competition_id": competition_id,
        "trigger_type": content.trigger_type.value,
        "status": content.status.value,
        "fire_policy": content.fire_policy.value,
        "target_competition_season_id": content.target_competition_season_id,
        "target_storyline_item_id": content.target_storyline_item_id,
        "origin_event_item_id": content.origin_event_item_id,
        "target_week": content.target_week,
        "target_at": content.target_at,
        "condition": values["condition"],
        "resolution_reason": content.resolution_reason,
    }


def _decode_trigger(row: Any) -> dict[str, Any]:
    return {
        "trigger_type": row.trigger_type,
        "status": row.status,
        "fire_policy": row.fire_policy,
        "target_storyline_item_id": row.target_storyline_item_id,
        "origin_event_item_id": row.origin_event_item_id,
        "target_competition_season_id": row.target_competition_season_id,
        "target_week": row.target_week,
        "target_at": row.target_at,
        "condition": row.condition,
        "resolution_reason": row.resolution_reason,
    }


def _encode_context_note(
    version_id: UUID,
    _competition_id: UUID,
    _generation_id: UUID,
    content: Any,
) -> dict[str, Any]:
    return {
        "version_id": version_id,
        "narrative_text": content.narrative,
        "outlook": content.outlook,
        "status": content.status.value,
        "tags": list(content.tags),
    }


def _decode_context_note(row: Any) -> dict[str, Any]:
    return {
        "narrative": row.narrative_text,
        "outlook": row.outlook,
        "status": row.status,
        "tags": row.tags,
    }


_CODECS = {
    (MemoryKind.STORYLINE, 1): _ContentCodec(
        StorylineVersion, _encode_storyline, _decode_storyline
    ),
    (MemoryKind.FACT, 1): _ContentCodec(FactVersion, _encode_fact, _decode_fact),
    (MemoryKind.EVENT, 1): _ContentCodec(EventVersion, _encode_event, _decode_event),
    (MemoryKind.TRIGGER, 1): _ContentCodec(
        TriggerVersion, _encode_trigger, _decode_trigger
    ),
    (MemoryKind.CONTEXT_NOTE, 1): _ContentCodec(
        ContextNoteVersion, _encode_context_note, _decode_context_note
    ),
}
