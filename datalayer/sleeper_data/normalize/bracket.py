"""Normalization helpers for playoff bracket data."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

from ..schema.models import PlayoffMatchup


def _extract_from_ref(
    ref: Any,
) -> tuple[Optional[int], Optional[str]]:
    """Parse a t1_from/t2_from dict into (matchup_id, outcome).

    The Sleeper API encodes bracket progression as {"w": matchup_id} or
    {"l": matchup_id}, indicating the winner or loser of a previous matchup.

    Returns:
        (matchup_id, outcome) where outcome is "w" or "l", or (None, None).
    """
    if not isinstance(ref, dict):
        return None, None
    if "w" in ref:
        return int(ref["w"]), "w"
    if "l" in ref:
        return int(ref["l"]), "l"
    return None, None


def normalize_bracket(
    raw_bracket: Iterable[Mapping[str, Any]],
    *,
    league_id: str,
    season: str,
    bracket_type: str,
) -> list[PlayoffMatchup]:
    """Normalize raw Sleeper bracket JSON into PlayoffMatchup dataclasses.

    Args:
        raw_bracket: List of bracket matchup dicts from Sleeper API.
        league_id: The league identifier.
        season: The season year string.
        bracket_type: "winners" or "losers".

    Returns:
        List of PlayoffMatchup dataclass instances.
    """
    rows: list[PlayoffMatchup] = []
    for entry in raw_bracket:
        round_num = entry.get("r")
        matchup_id = entry.get("m")
        if round_num is None or matchup_id is None:
            continue

        t1 = entry.get("t1")
        t2 = entry.get("t2")
        t1_roster_id = int(t1) if isinstance(t1, (int, float)) else None
        t2_roster_id = int(t2) if isinstance(t2, (int, float)) else None

        t1_from_matchup_id, t1_from_outcome = _extract_from_ref(entry.get("t1_from"))
        t2_from_matchup_id, t2_from_outcome = _extract_from_ref(entry.get("t2_from"))

        w = entry.get("w")
        l = entry.get("l")
        winner_roster_id = int(w) if isinstance(w, (int, float)) else None
        loser_roster_id = int(l) if isinstance(l, (int, float)) else None

        p = entry.get("p")
        placement = int(p) if isinstance(p, (int, float)) else None

        rows.append(
            PlayoffMatchup(
                league_id=league_id,
                season=season,
                bracket_type=bracket_type,
                round=int(round_num),
                matchup_id=int(matchup_id),
                t1_roster_id=t1_roster_id,
                t2_roster_id=t2_roster_id,
                t1_from_matchup_id=t1_from_matchup_id,
                t1_from_outcome=t1_from_outcome,
                t2_from_matchup_id=t2_from_matchup_id,
                t2_from_outcome=t2_from_outcome,
                winner_roster_id=winner_roster_id,
                loser_roster_id=loser_roster_id,
                placement=placement,
            )
        )
    return rows
