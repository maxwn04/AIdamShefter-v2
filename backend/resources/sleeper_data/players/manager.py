"""Global Sleeper player catalog reads."""

from __future__ import annotations

from typing import Any, cast

import sqlalchemy as sa

from backend.database.models.sleeper import Player as StoredPlayer
from backend.database.sessions import SessionFactory, read_only_session
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.sleeper_data.players.codec import decode_player
from backend.resources.sleeper_data.players.objects import Page, Player, PlayerSearch


class PlayerManager:
    """Read the latest observed global player catalog."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        # Player catalog rows are global, but construction remains competition scoped
        # so all resource managers share the same boundary contract.
        self._competition_id = context.scope.competition_id

    def search_players(self, query: PlayerSearch) -> Page[Player]:
        with read_only_session(self._session_factory) as session:
            predicates: list[Any] = []
            if query.text is not None:
                pattern = f"%{query.text.strip().casefold()}%"
                predicates.append(sa.func.lower(StoredPlayer.full_name).like(pattern))
            if query.position is not None:
                predicates.append(
                    sa.func.lower(StoredPlayer.position)
                    == query.position.strip().casefold()
                )
            if query.nfl_team is not None:
                predicates.append(
                    sa.func.lower(StoredPlayer.nfl_team)
                    == query.nfl_team.strip().casefold()
                )
            if query.active is not None:
                predicates.append(StoredPlayer.active.is_(query.active))
            where = sa.and_(*predicates) if predicates else sa.true()
            total = session.scalar(
                sa.select(sa.func.count()).select_from(StoredPlayer).where(where)
            )
            metadata_text = sa.cast(StoredPlayer.metadata_json, sa.Text).label(
                "metadata_text"
            )
            rows = session.execute(
                sa.select(
                    StoredPlayer,
                    metadata_text,
                )
                .where(where)
                .order_by(
                    sa.func.lower(StoredPlayer.full_name).nulls_last(),
                    StoredPlayer.sleeper_player_id,
                )
                .limit(query.limit)
                .offset(query.offset)
            ).all()
            return Page[Player](
                items=tuple(
                    decode_player(player, metadata) for player, metadata in rows
                ),
                total=cast(int, total),
                limit=query.limit,
                offset=query.offset,
            )
