"""Normalization helpers for matchup payloads."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable, Mapping

from ..schema.models import Game, MatchupRow


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value)


def normalize_matchups(
    raw_matchups: Iterable[Mapping[str, Any]],
    league_id: str,
    season: str,
    week: int,
) -> list[MatchupRow]:
    rows: list[MatchupRow] = []
    for raw_row in raw_matchups:
        matchup_id = raw_row.get("matchup_id")
        roster_id = raw_row.get("roster_id")
        if matchup_id is None or roster_id is None:
            continue
        rows.append(
            MatchupRow(
                league_id=str(league_id),
                season=str(season),
                week=int(week),
                matchup_id=int(matchup_id),
                roster_id=int(roster_id),
                points=float(raw_row.get("points", 0.0)),
                starters_json=_json_dumps(raw_row.get("starters")),
                players_json=_json_dumps(raw_row.get("players")),
                players_points_json=_json_dumps(raw_row.get("players_points")),
            )
        )
    return rows


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
