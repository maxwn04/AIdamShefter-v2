"""Decimal-safe JSON helpers shared by Sleeper resource packages."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from backend.services.datalayer.canonical_json import (
    JsonValue,
    canonical_json_bytes,
    parse_json_bytes,
)


def jsonb_expression(value: JsonValue) -> sa.ColumnElement[Any]:
    """Bind exact canonical JSON text and let PostgreSQL parse it as JSONB."""

    text_value = canonical_json_bytes(value).decode("utf-8")
    return sa.cast(sa.literal(text_value, type_=sa.Text()), JSONB)


def parse_jsonb_text(value: str) -> JsonValue:
    return parse_json_bytes(value.encode("utf-8"))
