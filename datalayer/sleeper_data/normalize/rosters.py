"""Normalization helpers for roster payloads."""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from ..schema.models import Roster, TeamProfile


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value)


def normalize_rosters(
    raw_rosters: Iterable[Mapping[str, Any]], league_id: str
) -> list[Roster]:
    rosters: list[Roster] = []
    for raw_roster in raw_rosters:
        rosters.append(
            Roster(
                league_id=str(league_id),
                roster_id=int(raw_roster["roster_id"]),
                owner_user_id=raw_roster.get("owner_id"),
                settings_json=_json_dumps(raw_roster.get("settings")),
                metadata_json=_json_dumps(raw_roster.get("metadata")),
            )
        )
    return rosters


def _first_metadata_value(metadata: Mapping[str, Any] | None, keys: Iterable[str]) -> str | None:
    if not metadata:
        return None
    for key in keys:
        value = metadata.get(key)
        if value:
            return str(value)
    return None


def _avatar_url(avatar_id: str | None) -> str | None:
    if not avatar_id:
        return None
    return f"https://sleepercdn.com/avatars/{avatar_id}"


def derive_team_profiles(
    raw_rosters: Iterable[Mapping[str, Any]],
    raw_users: Iterable[Mapping[str, Any]],
    league_id: str,
) -> list[TeamProfile]:
    user_by_id: dict[str, Mapping[str, Any]] = {
        str(user["user_id"]): user for user in raw_users
    }

    profiles: list[TeamProfile] = []
    for raw_roster in raw_rosters:
        owner_id = raw_roster.get("owner_id")
        user = user_by_id.get(str(owner_id)) if owner_id is not None else None
        metadata = raw_roster.get("metadata") or {}
        team_name = _first_metadata_value(
            metadata, ("team_name", "name", "team_name2")
        )
        display_name = None
        avatar_id = None
        if user:
            display_name = user.get("display_name") or user.get("username")
            avatar_id = user.get("avatar")
        if not avatar_id:
            avatar_id = metadata.get("avatar")

        profiles.append(
            TeamProfile(
                league_id=str(league_id),
                roster_id=int(raw_roster["roster_id"]),
                team_name=team_name or (str(display_name) if display_name else None),
                manager_name=str(display_name) if display_name else None,
                avatar_url=_avatar_url(avatar_id),
            )
        )
    return profiles
