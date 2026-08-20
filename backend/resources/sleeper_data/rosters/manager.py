"""Competition-scoped current roster reads."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa

from backend.database.models.core import Franchise, SeasonRoster
from backend.database.models.sleeper import Player as StoredPlayer
from backend.database.models.sleeper import Roster as StoredRoster
from backend.database.models.sleeper import RosterManager as StoredRosterManager
from backend.database.models.sleeper import RosterPlayer as StoredRosterPlayer
from backend.database.models.sleeper import User as StoredUser
from backend.database.sessions import SessionFactory, read_only_session
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.sleeper_data.common.codec import parse_jsonb_text
from backend.resources.sleeper_data.players.codec import decode_player
from backend.resources.sleeper_data.rosters.objects import (
    RosterManagerAssignment,
    RosterPlayer,
    SeasonRosterState,
)
from backend.services.datalayer.errors import DatalayerResourceNotFound


class RosterManager:
    """Read latest roster state within one competition."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id

    def get_roster(self, season_roster_id: UUID) -> SeasonRosterState:
        with read_only_session(self._session_factory) as session:
            settings_text = sa.cast(StoredRoster.settings_json, sa.Text).label(
                "settings_text"
            )
            metadata_text = sa.cast(StoredRoster.metadata_json, sa.Text).label(
                "metadata_text"
            )
            row = session.execute(
                sa.select(
                    SeasonRoster,
                    Franchise,
                    StoredRoster,
                    settings_text,
                    metadata_text,
                )
                .join(Franchise, Franchise.id == SeasonRoster.franchise_id)
                .join(StoredRoster, StoredRoster.season_roster_id == SeasonRoster.id)
                .where(
                    SeasonRoster.id == season_roster_id,
                    SeasonRoster.competition_id == self._competition_id,
                )
            ).one_or_none()
            if row is None:
                raise DatalayerResourceNotFound("season_roster", str(season_roster_id))
            identity, franchise, stored, settings, metadata = row
            manager_rows = session.execute(
                sa.select(StoredRosterManager, StoredUser)
                .join(
                    StoredUser,
                    StoredUser.sleeper_user_id == StoredRosterManager.sleeper_user_id,
                )
                .where(StoredRosterManager.season_roster_id == identity.id)
                .order_by(
                    StoredRosterManager.source_order,
                    StoredRosterManager.sleeper_user_id,
                )
            ).all()
            player_order = (
                StoredRosterPlayer.role,
                StoredRosterPlayer.sleeper_player_id,
            )
            player_rows = session.execute(
                sa.select(
                    StoredRosterPlayer,
                    StoredPlayer,
                    sa.cast(StoredPlayer.metadata_json, sa.Text).label(
                        "player_metadata_text"
                    ),
                )
                .join(
                    StoredPlayer,
                    StoredPlayer.sleeper_player_id
                    == StoredRosterPlayer.sleeper_player_id,
                )
                .where(StoredRosterPlayer.season_roster_id == identity.id)
                .order_by(*player_order)
            ).all()
            return SeasonRosterState(
                season_roster_id=identity.id,
                competition_season_id=identity.competition_season_id,
                franchise_id=identity.franchise_id,
                sleeper_roster_id=identity.sleeper_roster_id,
                franchise_name=franchise.display_name,
                settings=cast(dict[str, Any], parse_jsonb_text(settings)),
                metadata=cast(dict[str, Any], parse_jsonb_text(metadata)),
                record_string=stored.record_string,
                wins=stored.wins,
                losses=stored.losses,
                ties=stored.ties,
                points_for=stored.points_for,
                points_against=stored.points_against,
                managers=tuple(
                    RosterManagerAssignment(
                        sleeper_user_id=manager.sleeper_user_id,
                        display_name=user.display_name,
                        role=cast(Any, manager.role),
                        source_order=manager.source_order,
                    )
                    for manager, user in manager_rows
                ),
                players=tuple(
                    RosterPlayer(
                        player=decode_player(player, player_metadata),
                        role=cast(Any, membership.role),
                    )
                    for membership, player, player_metadata in player_rows
                ),
                source_api_request_id=stored.source_api_request_id,
            )
