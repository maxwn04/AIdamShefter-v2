"""Decimal-first JSON parsing, canonical encoding, and payload identity."""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from typing import NoReturn

from typing_extensions import TypeAliasType


JsonValue = TypeAliasType(
    "JsonValue",
    (
        type(None)
        | bool
        | int
        | Decimal
        | str
        | list["JsonValue"]
        | dict[str, "JsonValue"]
    ),
)


def parse_json_bytes(content: bytes) -> JsonValue:
    """Parse JSON without routing fractional source values through float."""

    return json.loads(
        content,
        parse_float=Decimal,
        parse_int=int,
        parse_constant=_reject_non_finite,
    )


def canonical_json_bytes(value: JsonValue) -> bytes:
    """Encode one JSON value as deterministic compact UTF-8 bytes."""

    return _encode(value).encode("utf-8")


def canonical_json_sha256(value: JsonValue) -> str:
    """Return the lowercase SHA-256 identity of canonical JSON bytes."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _encode(value: JsonValue) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("JSON numbers must be finite")
        if value.is_zero():
            return "0"
        return format(value.normalize(), "f")
    if isinstance(value, float):
        raise TypeError("binary floats are not accepted at the Sleeper boundary")
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("JSON object keys must be strings")
        return "{" + ",".join(
            f"{_encode(key)}:{_encode(value[key])}" for key in sorted(value)
        ) + "}"
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _reject_non_finite(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")
