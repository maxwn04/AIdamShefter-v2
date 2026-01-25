"""Normalization helpers for matchup payloads."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

from ..schema.models import Game, MatchupRow, PlayerPerformance


def _normalize_player_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(pid) for pid in value if pid]


def _normalize_player_points(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    points: dict[str, float] = {}
    for player_id, raw_points in value.items():
        if player_id is None:
            continue
        try:
            points[str(player_id)] = float(raw_points)
        except (TypeError, ValueError):
            continue
    return points


def normalize_matchups(
    raw_matchups: Iterable[Mapping[str, Any]],
    league_id: str,
    season: str,
    week: int,
) -> tuple[list[MatchupRow], list[PlayerPerformance]]:
    rows: list[MatchupRow] = []
    performance_rows: list[PlayerPerformance] = []
    for raw_row in raw_matchups:
        matchup_id = raw_row.get("matchup_id")
        roster_id = raw_row.get("roster_id")
        if matchup_id is None or roster_id is None:
            continue
        matchup_row = MatchupRow(
            league_id=str(league_id),
            season=str(season),
            week=int(week),
            matchup_id=int(matchup_id),
            roster_id=int(roster_id),
            points=float(raw_row.get("points", 0.0)),
        )
        rows.append(matchup_row)

        players = _normalize_player_ids(raw_row.get("players"))
        starters = set(_normalize_player_ids(raw_row.get("starters")))
        points = _normalize_player_points(raw_row.get("players_points"))
        for player_id in players:
            performance_rows.append(
                PlayerPerformance(
                    league_id=matchup_row.league_id,
                    season=matchup_row.season,
                    week=matchup_row.week,
                    player_id=str(player_id),
                    roster_id=matchup_row.roster_id,
                    matchup_id=matchup_row.matchup_id,
                    points=points.get(str(player_id), 0.0),
                    role="starter" if player_id in starters else "bench",
                )
            )
    return rows, performance_rows


def derive_games(
    matchup_rows: Iterable[MatchupRow],
    *,
    is_playoffs: bool,
) -> list[Game]:
    games: list[Game] = []
    grouped: dict[tuple[int, int], list[MatchupRow]] = defaultdict(list)
    for row in matchup_rows:
        grouped[(row.week, row.matchup_id)].append(row)

    for (week, matchup_id), rows in grouped.items():
        if len(rows) < 2:
            # Skip unpaired rows rather than inventing a self-match.
            continue

        row_a, row_b = rows[0], rows[1]
        if row_a.points > row_b.points:
            winner = row_a.roster_id
        elif row_b.points > row_a.points:
            winner = row_b.roster_id
        else:
            winner = None

        games.append(
            Game(
                league_id=row_a.league_id,
                season=row_a.season,
                week=row_a.week,
                matchup_id=matchup_id,
                roster_id_a=row_a.roster_id,
                roster_id_b=row_b.roster_id,
                points_a=row_a.points,
                points_b=row_b.points,
                winner_roster_id=winner,
                is_playoffs=is_playoffs,
            )
        )
    return games
