"""Normalization helpers for player payloads."""

from __future__ import annotations

import json
from typing import Any, Mapping

from ..schema.models import Player


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value)


def _full_name(raw_player: Mapping[str, Any]) -> str | None:
    name = raw_player.get("full_name")
    if name:
        return str(name)
    first = raw_player.get("first_name")
    last = raw_player.get("last_name")
    if first and last:
        return f"{first} {last}"
    return None


def normalize_players(raw_players: Mapping[str, Any]) -> list[Player]:
    rows: list[Player] = []
    for player_id, raw_player in raw_players.items():
        rows.append(
            Player(
                player_id=str(raw_player.get("player_id") or player_id),
                full_name=_full_name(raw_player),
                position=raw_player.get("position"),
                nfl_team=raw_player.get("team"),
                status=raw_player.get("status"),
                injury_status=raw_player.get("injury_status"),
                age=raw_player.get("age"),
                years_exp=raw_player.get("years_exp"),
                metadata_json=_json_dumps(raw_player),
                updated_at=raw_player.get("updated_at"),
            )
        )
    return rows
