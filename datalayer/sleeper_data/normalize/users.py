"""Normalization helpers for user payloads."""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from ..schema.models import User


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value)


def normalize_users(raw_users: Iterable[Mapping[str, Any]]) -> list[User]:
    users: list[User] = []
    for raw_user in raw_users:
        display_name = raw_user.get("display_name") or raw_user.get("username") or ""
        users.append(
            User(
                user_id=str(raw_user["user_id"]),
                display_name=str(display_name),
                avatar=raw_user.get("avatar"),
                metadata_json=_json_dumps(raw_user.get("metadata")),
            )
        )
    return users
