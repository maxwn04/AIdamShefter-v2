"""Normalization helpers for standings snapshots."""

from __future__ import annotations

from typing import Iterable, Mapping

from ..schema.models import StandingsWeek


def _points_from_settings(settings: Mapping[str, int | float | None], *, prefix: str) -> float:
    whole = settings.get(prefix, 0) or 0
    decimal = settings.get(f"{prefix}_decimal", 0) or 0
    return float(whole) + float(decimal) / 100.0


def normalize_standings(
    raw_rosters: Iterable[Mapping[str, object]],
    league_id: str,
    season: str,
    week: int,
) -> list[StandingsWeek]:
    rows: list[StandingsWeek] = []
    for raw_roster in raw_rosters:
        settings = raw_roster.get("settings") or {}
        rows.append(
            StandingsWeek(
                league_id=str(league_id),
                season=str(season),
                week=int(week),
                roster_id=int(raw_roster["roster_id"]),
                wins=int(settings.get("wins", 0) or 0),
                losses=int(settings.get("losses", 0) or 0),
                ties=int(settings.get("ties", 0) or 0),
                points_for=_points_from_settings(settings, prefix="fpts"),
                points_against=_points_from_settings(settings, prefix="fpts_against"),
                rank=(int(settings["rank"]) if settings.get("rank") is not None else None),
                streak_type=settings.get("streak_type"),
                streak_len=(
                    int(settings["streak_length"])
                    if settings.get("streak_length") is not None
                    else None
                ),
            )
        )
    return rows
