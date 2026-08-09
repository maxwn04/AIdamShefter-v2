"""Opaque, versioned pagination cursors for memory collections."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from dataclasses import dataclass
import json
from uuid import UUID

from backend.resources.memory.errors import InvalidMemoryCursor


_CURSOR_VERSION = 1


@dataclass(frozen=True, slots=True)
class MemoryItemCursor:
    revision_id: UUID
    item_id: UUID


@dataclass(frozen=True, slots=True)
class MemoryRevisionCursor:
    competition_id: UUID
    sequence_number: int


def encode_item_cursor(revision_id: UUID, item_id: UUID) -> str:
    return _encode(
        {
            "v": _CURSOR_VERSION,
            "kind": "item",
            "revision": str(revision_id),
            "item": str(item_id),
        }
    )


def decode_item_cursor(value: str) -> MemoryItemCursor:
    payload = _decode(value, "item")
    try:
        return MemoryItemCursor(
            revision_id=UUID(payload["revision"]),
            item_id=UUID(payload["item"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise _invalid() from error


def encode_revision_cursor(competition_id: UUID, sequence_number: int) -> str:
    return _encode(
        {
            "v": _CURSOR_VERSION,
            "kind": "revision",
            "competition": str(competition_id),
            "sequence": sequence_number,
        }
    )


def decode_revision_cursor(value: str) -> MemoryRevisionCursor:
    payload = _decode(value, "revision")
    try:
        sequence_number = payload["sequence"]
        if isinstance(sequence_number, bool) or not isinstance(sequence_number, int):
            raise TypeError
        cursor = MemoryRevisionCursor(
            competition_id=UUID(payload["competition"]),
            sequence_number=sequence_number,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise _invalid() from error
    if cursor.sequence_number < 0:
        raise _invalid()
    return cursor


def _encode(payload: dict[str, object]) -> str:
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return urlsafe_b64encode(serialized).decode("ascii").rstrip("=")


def _decode(value: str, kind: str) -> dict[str, object]:
    try:
        padding = "=" * (-len(value) % 4)
        decoded = urlsafe_b64decode(value + padding)
        payload = json.loads(decoded)
    except (
        Base64Error,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise _invalid() from error
    if (
        not isinstance(payload, dict)
        or payload.get("v") != _CURSOR_VERSION
        or payload.get("kind") != kind
    ):
        raise _invalid()
    return payload


def _invalid() -> InvalidMemoryCursor:
    return InvalidMemoryCursor("invalid memory pagination cursor")
