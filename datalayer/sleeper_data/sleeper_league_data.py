"""Facade for loading Sleeper league data into SQLite."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from .config import SleeperConfig, load_config
from .normalize import (
    derive_games,
    derive_team_profiles,
    normalize_league,
    normalize_matchups,
    normalize_players,
    normalize_roster_players,
    normalize_rosters,
    normalize_standings,
    normalize_transaction_moves,
    normalize_transactions,
    normalize_users,
)
from .schema.models import SeasonContext
from .schema.models import DraftPick
from .sleeper_api import (
    SleeperClient,
    get_league,
    get_league_rosters,
    get_league_users,
    get_matchups,
    get_players,
    get_state,
    get_traded_picks,
    get_transactions as api_get_transactions,
)
from .store.sqlite_store import bulk_insert, create_tables
from .queries.defaults import (
    get_league_snapshot,
    get_player_summary,
    get_roster_current,
    get_roster_snapshot,
    get_team_dossier,
    get_transactions as query_get_transactions,
    get_week_games,
)
from .queries.sql_tool import run_sql


class SleeperLeagueData:
    def __init__(
        self,
        league_id: Optional[str] = None,
        *,
        client: Optional[SleeperClient] = None,
        config: Optional[SleeperConfig] = None,
    ) -> None:
        resolved_config = config or load_config()
        self.league_id = league_id or resolved_config.league_id
        self.week_override = resolved_config.week_override
        self.client = client or SleeperClient()
        self.conn: Optional[sqlite3.Connection] = None

    def load(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        create_tables(self.conn)

        raw_league = get_league(self.league_id, client=self.client)
        raw_users = get_league_users(self.league_id, client=self.client)
        raw_rosters = get_league_rosters(self.league_id, client=self.client)
        raw_state = get_state("nfl", client=self.client)

        league = normalize_league(raw_league)
        users = normalize_users(raw_users)
        rosters = normalize_rosters(raw_rosters, league_id=self.league_id)
        roster_players = normalize_roster_players(raw_rosters, league_id=self.league_id)
        team_profiles = derive_team_profiles(raw_rosters, raw_users, league_id=self.league_id)

        bulk_insert(self.conn, league.table_name, [league])
        if users:
            bulk_insert(self.conn, users[0].table_name, users)
        if rosters:
            bulk_insert(self.conn, rosters[0].table_name, rosters)
        if team_profiles:
            bulk_insert(self.conn, team_profiles[0].table_name, team_profiles)

        draft_rounds = int((raw_league.get("settings") or {}).get("draft_rounds") or 0)
        base_season = league.season
        try:
            base_year = int(base_season)
        except (TypeError, ValueError):
            base_year = None

        draft_picks: list[DraftPick] = []
        if base_year and draft_rounds > 0 and rosters:
            for season_offset in range(1, 4):
                season_value = str(base_year + season_offset)
                for roster in rosters:
                    for round_value in range(1, draft_rounds + 1):
                        draft_picks.append(
                            DraftPick(
                                league_id=self.league_id,
                                season=season_value,
                                round=round_value,
                                original_roster_id=roster.roster_id,
                                current_roster_id=roster.roster_id,
                                pick_id=None,
                                source="seed",
                            )
                        )

        if draft_picks:
            bulk_insert(self.conn, draft_picks[0].table_name, draft_picks)

        traded_picks = get_traded_picks(self.league_id, client=self.client)
        for pick in traded_picks or []:
            season_value = pick.get("season")
            round_value = pick.get("round")
            original_roster_id = pick.get("roster_id")
            owner_id = pick.get("owner_id")
            if season_value is None or round_value is None or original_roster_id is None:
                continue
            if owner_id is None:
                continue
            self.conn.execute(
                """
                UPDATE draft_picks
                SET current_roster_id = :current_roster_id
                WHERE league_id = :league_id
                  AND season = :season
                  AND round = :round
                  AND original_roster_id = :original_roster_id
                """,
                {
                    "current_roster_id": int(owner_id),
                    "league_id": self.league_id,
                    "season": str(season_value),
                    "round": int(round_value),
                    "original_roster_id": int(original_roster_id),
                },
            )

        computed_week = int(raw_state.get("week") or 0)
        effective_week = int(self.week_override or computed_week or 0)
        season = str(raw_league.get("season") or raw_state.get("season") or "")

        if effective_week > 0:
            for week in range(1, effective_week + 1):
                raw_matchups = get_matchups(self.league_id, week, client=self.client)
                matchup_rows = normalize_matchups(
                    raw_matchups, league_id=self.league_id, season=season, week=week
                )
                games = derive_games(matchup_rows, is_playoffs=False)
                if matchup_rows:
                    bulk_insert(self.conn, matchup_rows[0].table_name, matchup_rows)
                if games:
                    bulk_insert(self.conn, games[0].table_name, games)

                raw_transactions = api_get_transactions(
                    self.league_id, week, client=self.client
                )
                transactions = normalize_transactions(
                    raw_transactions, league_id=self.league_id, season=season, week=week
                )
                moves = normalize_transaction_moves(raw_transactions)
                if transactions:
                    bulk_insert(self.conn, transactions[0].table_name, transactions)
                if moves:
                    bulk_insert(self.conn, moves[0].table_name, moves)

            standings = normalize_standings(
                raw_rosters, league_id=self.league_id, season=season, week=effective_week
            )
            if standings:
                bulk_insert(self.conn, standings[0].table_name, standings)

        raw_players = get_players("nfl", client=self.client)
        players = normalize_players(raw_players)
        if players:
            bulk_insert(self.conn, players[0].table_name, players)
        if roster_players:
            bulk_insert(self.conn, roster_players[0].table_name, roster_players)

        season_context = SeasonContext(
            league_id=self.league_id,
            computed_week=computed_week,
            override_week=self.week_override,
            effective_week=effective_week,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        bulk_insert(self.conn, season_context.table_name, [season_context])

    def save_to_file(self, output_path: str) -> str:
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before saving.")

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        file_conn = sqlite3.connect(output_path)
        try:
            self.conn.backup(file_conn)
            file_conn.commit()
        finally:
            file_conn.close()

        return output_path

    def get_league_snapshot(self, week: int | None = None) -> dict[str, Any]:
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return get_league_snapshot(self.conn, week)

    def get_team_dossier(self, roster_key: Any, week: int | None = None) -> dict[str, Any]:
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return get_team_dossier(self.conn, self.league_id, roster_key, week)

    def get_week_games(
        self,
        week: int | None = None,
        roster_key: Any | None = None,
        *,
        include_players: bool = False,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        if week is None:
            context = self.conn.execute(
                "SELECT effective_week FROM season_context LIMIT 1"
            ).fetchone()
            if context:
                week = context[0]
        if week is None:
            return []
        return get_week_games(
            self.conn,
            self.league_id,
            int(week),
            roster_key=roster_key,
            include_players=include_players,
        )

    def get_transactions(
        self, week_from: int, week_to: int, roster_key: Any | None = None
    ) -> list[dict[str, Any]]:
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return query_get_transactions(
            self.conn, self.league_id, week_from, week_to, roster_key=roster_key
        )

    def get_player_summary(self, player_key: Any, week_to: int | None = None) -> dict[str, Any]:
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return get_player_summary(self.conn, player_key, week_to)

    def get_roster_current(self, roster_key: Any) -> dict[str, Any]:
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return get_roster_current(self.conn, self.league_id, roster_key)

    def get_roster_snapshot(self, roster_key: Any, week: int) -> dict[str, Any]:
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return get_roster_snapshot(self.conn, self.league_id, roster_key, week)

    def run_sql(
        self,
        query: str,
        params: Mapping[str, Any] | None = None,
        *,
        limit: int = 200,
    ) -> dict[str, Any]:
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return run_sql(self.conn, query, params, limit=limit)
