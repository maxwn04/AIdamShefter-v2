"""Normalization helpers for league payloads."""

from __future__ import annotations

import json
from typing import Any, Mapping

from ..schema.models import League


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_league(raw_league: Mapping[str, Any]) -> League:
    settings = raw_league.get("settings") or {}
    league_average_match = _int_or_none(settings.get("league_average_match"))
    playoff_week_start = _int_or_none(
        raw_league.get("playoff_week_start") or settings.get("playoff_week_start")
    )
    playoff_teams = _int_or_none(
        raw_league.get("playoff_teams") or settings.get("playoff_teams")
    )
    return League(
        league_id=str(raw_league["league_id"]),
        season=str(raw_league.get("season", "")),
        name=str(raw_league.get("name", "")),
        sport=str(raw_league.get("sport", "")),
        scoring_settings_json=_json_dumps(raw_league.get("scoring_settings")),
        roster_positions_json=_json_dumps(raw_league.get("roster_positions")),
        playoff_week_start=playoff_week_start,
        playoff_teams=playoff_teams,
        league_average_match=league_average_match,
    )
