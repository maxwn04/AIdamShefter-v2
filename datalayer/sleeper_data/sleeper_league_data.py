"""Facade for loading Sleeper league data into SQLite."""

from __future__ import annotations

import os
import sqlite3
from typing import Optional

from .config import SleeperConfig, load_config
from .normalize import derive_team_profiles, normalize_league, normalize_rosters, normalize_users
from .sleeper_api import SleeperClient, get_league, get_league_rosters, get_league_users
from .store.sqlite_store import bulk_insert, create_tables


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

        league = normalize_league(raw_league)
        users = normalize_users(raw_users)
        rosters = normalize_rosters(raw_rosters, league_id=self.league_id)
        team_profiles = derive_team_profiles(raw_rosters, raw_users, league_id=self.league_id)

        bulk_insert(self.conn, league.table_name, [league])
        if users:
            bulk_insert(self.conn, users[0].table_name, users)
        if rosters:
            bulk_insert(self.conn, rosters[0].table_name, rosters)
        if team_profiles:
            bulk_insert(self.conn, team_profiles[0].table_name, team_profiles)

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
