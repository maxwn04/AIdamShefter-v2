"""Player ORM-to-resource decoding."""

from __future__ import annotations

from typing import Any, cast

from backend.database.models.sleeper import Player as StoredPlayer
from backend.resources.sleeper_data.common.codec import parse_jsonb_text
from backend.resources.sleeper_data.players.objects import Player


def decode_player(stored: StoredPlayer, metadata_text: str) -> Player:
    return Player(
        sleeper_player_id=stored.sleeper_player_id,
        full_name=stored.full_name,
        position=stored.position,
        nfl_team=stored.nfl_team,
        active=stored.active,
        status=stored.status,
        injury_status=stored.injury_status,
        age=stored.age,
        years_experience=stored.years_experience,
        metadata=cast(dict[str, Any], parse_jsonb_text(metadata_text)),
        source_api_request_id=stored.source_api_request_id,
    )
