"""Deterministic hashing for one complete visible canonical memory state.

This module is package-internal.  It accepts logical typed state, never a
caller-computed digest, and deliberately excludes revision/projection mechanics.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
import math
from typing import Any
from uuid import UUID

import cbor2

from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.context_notes.objects import (
    CompetitionContextNoteIdentity,
    CompetitionSeasonContextNoteIdentity,
    ContextNoteIdentity,
    FranchiseContextNoteIdentity,
)


STATE_HASH_FORMAT = "aidam.memory.state.v1"
STATE_HASH_PREFIX = "sha256-cbor-v1:"


@dataclass(frozen=True, slots=True)
class StoredSchemaContent:
    """One resource codec's exact retained content-schema payload."""

    memory_kind: MemoryKind
    schema_version: int
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class StateHashItem:
    """The logical fields of one version visible in the resulting state.

    Creation/recording provenance and introduced/retired revision IDs are not
    inputs.  The latter select which version is visible; they are not part of
    the resulting logical state itself.
    """

    item_id: UUID
    kind: MemoryKind
    agent_key: str | None
    context_note_identity: ContextNoteIdentity | None
    version_id: UUID
    revision_number: int
    content_schema_version: int
    competition_season_id: UUID | None
    week: int | None
    occurred_at: datetime | None
    content: StoredSchemaContent


def compute_state_content_hash(
    competition_id: UUID,
    items: Iterable[StateHashItem],
) -> str:
    """Hash a competition's complete visible logical state.

    Items are sorted by their canonical UUID strings, then the versioned
    envelope is encoded using RFC 8949 deterministic CBOR and SHA-256.  The
    empty item sequence is the canonical empty-root state.
    """

    materialized = tuple(items)
    _validate_state_items(materialized)
    ordered = sorted(materialized, key=_state_item_sort_key)
    envelope = {
        "format": STATE_HASH_FORMAT,
        "competition_id": _canonical_uuid(competition_id),
        "items": [_state_item_payload(item) for item in ordered],
    }
    encoded = cbor2.dumps(envelope, canonical=True)
    return f"{STATE_HASH_PREFIX}{sha256(encoded).hexdigest()}"


def state_hash_item(
    *,
    item_id: UUID,
    kind: MemoryKind,
    agent_key: str | None,
    version_id: UUID,
    revision_number: int,
    content_schema_version: int,
    competition_season_id: UUID | None,
    week: int | None,
    occurred_at: datetime | None,
    content: StoredSchemaContent,
    context_note_identity: ContextNoteIdentity | None = None,
) -> StateHashItem:
    """Construct one logical state value without exposing ORM rows."""

    return StateHashItem(
        item_id=item_id,
        kind=kind,
        agent_key=agent_key,
        context_note_identity=context_note_identity,
        version_id=version_id,
        revision_number=revision_number,
        content_schema_version=content_schema_version,
        competition_season_id=competition_season_id,
        week=week,
        occurred_at=occurred_at,
        content=content,
    )


def _state_item_payload(item: StateHashItem) -> dict[str, Any]:
    return {
        "item_id": _canonical_uuid(item.item_id),
        "kind": item.kind.value,
        "agent_key": item.agent_key,
        "context_note_identity": _context_note_identity_payload(
            item.context_note_identity
        ),
        "version_id": _canonical_uuid(item.version_id),
        "revision_number": item.revision_number,
        "content_schema_version": item.content_schema_version,
        "competition_season_id": (
            _canonical_uuid(item.competition_season_id)
            if item.competition_season_id is not None
            else None
        ),
        "week": item.week,
        "occurred_at": _canonical_datetime(item.occurred_at),
        "content": _canonical_value(item.content.payload),
    }


def _validate_state_items(items: tuple[StateHashItem, ...]) -> None:
    item_ids: set[UUID] = set()
    version_ids: set[UUID] = set()
    for item in items:
        if item.item_id in item_ids:
            raise ValueError(f"visible state repeats memory item {item.item_id}")
        if item.version_id in version_ids:
            raise ValueError(f"visible state repeats memory version {item.version_id}")
        item_ids.add(item.item_id)
        version_ids.add(item.version_id)

        if item.agent_key is not None and not item.agent_key.strip():
            raise ValueError("agent_key must be nonblank when present")
        if item.revision_number <= 0:
            raise ValueError("revision_number must be positive")
        if item.content_schema_version <= 0:
            raise ValueError("content_schema_version must be positive")
        if item.week is not None and item.week < 0:
            raise ValueError("week must be non-negative when present")
        if item.occurred_at is not None and item.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware when present")
        if item.content.memory_kind is not item.kind:
            raise ValueError("memory kind does not match typed content")
        if item.content.schema_version <= 0:
            raise ValueError("stored content schema version must be positive")
        if item.content.schema_version != item.content_schema_version:
            raise ValueError("content schema version does not match its envelope")

        has_note_identity = item.context_note_identity is not None
        if has_note_identity != (item.kind is MemoryKind.CONTEXT_NOTE):
            raise ValueError(
                "context-note identity is required exactly for context-note state"
            )


def _state_item_sort_key(item: StateHashItem) -> tuple[str, str]:
    return (_canonical_uuid(item.item_id), _canonical_uuid(item.version_id))


def _context_note_identity_payload(
    identity: ContextNoteIdentity | None,
) -> dict[str, Any] | None:
    if identity is None:
        return None
    if isinstance(identity, CompetitionContextNoteIdentity):
        return {
            "scope": "competition",
            "note_key": identity.note_key,
        }
    if isinstance(identity, CompetitionSeasonContextNoteIdentity):
        return {
            "scope": "competition_season",
            "competition_season_id": _canonical_uuid(
                identity.competition_season_id
            ),
            "note_key": identity.note_key,
        }
    if isinstance(identity, FranchiseContextNoteIdentity):
        return {
            "scope": "franchise",
            "franchise_id": _canonical_uuid(identity.franchise_id),
            "note_key": identity.note_key,
        }
    raise TypeError(
        f"unsupported context-note identity: {type(identity).__name__}"
    )


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, UUID):
        return _canonical_uuid(value)
    if isinstance(value, datetime):
        return _canonical_datetime(value)
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical memory state cannot contain non-finite numbers")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical memory mappings require string keys")
            normalized[key] = _canonical_value(nested)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_canonical_value(nested) for nested in value]
    raise TypeError(f"unsupported canonical memory value: {type(value).__name__}")


def _canonical_uuid(value: UUID) -> str:
    return str(value)


def _canonical_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.utcoffset() is None:
        raise ValueError("canonical memory datetimes must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
