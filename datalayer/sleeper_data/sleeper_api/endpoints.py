"""Sleeper API endpoint helpers."""

from __future__ import annotations

from typing import Any, Optional

from .client import SleeperClient


def _client_or_default(client: Optional[SleeperClient]) -> SleeperClient:
    return client or SleeperClient()


def get_league(league_id: str, client: Optional[SleeperClient] = None) -> dict[str, Any]:
    return _client_or_default(client).get_json(f"/league/{league_id}")


def get_league_users(
    league_id: str, client: Optional[SleeperClient] = None
) -> list[dict[str, Any]]:
    return _client_or_default(client).get_json(f"/league/{league_id}/users")


def get_league_rosters(
    league_id: str, client: Optional[SleeperClient] = None
) -> list[dict[str, Any]]:
    return _client_or_default(client).get_json(f"/league/{league_id}/rosters")


def get_matchups(
    league_id: str, week: int, client: Optional[SleeperClient] = None
) -> list[dict[str, Any]]:
    return _client_or_default(client).get_json(f"/league/{league_id}/matchups/{week}")


def get_transactions(
    league_id: str, week: int, client: Optional[SleeperClient] = None
) -> list[dict[str, Any]]:
    return _client_or_default(client).get_json(f"/league/{league_id}/transactions/{week}")


def get_traded_picks(
    league_id: str, client: Optional[SleeperClient] = None
) -> list[dict[str, Any]]:
    return _client_or_default(client).get_json(f"/league/{league_id}/traded_picks")


def get_players(
    sport: str = "nfl", client: Optional[SleeperClient] = None
) -> dict[str, Any]:
    return _client_or_default(client).get_json(f"/players/{sport}")


def get_winners_bracket(
    league_id: str, client: Optional[SleeperClient] = None
) -> list[dict[str, Any]]:
    return _client_or_default(client).get_json(f"/league/{league_id}/winners_bracket")


def get_losers_bracket(
    league_id: str, client: Optional[SleeperClient] = None
) -> list[dict[str, Any]]:
    return _client_or_default(client).get_json(f"/league/{league_id}/losers_bracket")


def get_state(sport: str = "nfl", client: Optional[SleeperClient] = None) -> dict[str, Any]:
    return _client_or_default(client).get_json(f"/state/{sport}")
