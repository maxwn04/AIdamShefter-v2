"""Current normalized Sleeper data models."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class League(Base):
    __tablename__ = "leagues"
    __table_args__ = (
        Index("ix_leagues_source_request", "source_api_request_id"),
        {"schema": "sleeper"},
    )

    competition_season_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.competition_seasons.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    source_api_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sleeper.api_requests.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    season: Mapped[str] = mapped_column(Text)
    previous_sleeper_league_id: Mapped[str | None] = mapped_column(Text)
    sleeper_draft_id: Mapped[str | None] = mapped_column(Text)
    sport: Mapped[str] = mapped_column(Text, server_default=text("'nfl'"))
    scoring_settings: Mapped[dict[str, Any]] = mapped_column(JSONB)
    roster_positions: Mapped[list[Any]] = mapped_column(JSONB)
    provider_settings: Mapped[dict[str, Any]] = mapped_column(JSONB)
    playoff_start_week: Mapped[int | None] = mapped_column(SmallInteger)
    playoff_team_count: Mapped[int | None] = mapped_column(SmallInteger)
    league_average_match: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_display_name_lower", func.lower(text("display_name"))),
        {"schema": "sleeper"},
    )

    sleeper_user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text)
    username: Mapped[str | None] = mapped_column(Text)
    avatar: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)
    source_api_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sleeper.api_requests.id", ondelete="RESTRICT")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LeagueUser(Base):
    __tablename__ = "league_users"
    __table_args__ = (
        Index("ix_league_users_user", "sleeper_user_id"),
        {"schema": "sleeper"},
    )

    competition_season_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.competition_seasons.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    sleeper_user_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("sleeper.users.sleeper_user_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    team_name: Mapped[str | None] = mapped_column(Text)
    nickname: Mapped[str | None] = mapped_column(Text)
    is_commissioner: Mapped[bool] = mapped_column(server_default=text("false"))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)
    source_api_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sleeper.api_requests.id", ondelete="RESTRICT")
    )


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        Index("ix_players_full_name_lower", func.lower(text("full_name"))),
        Index("ix_players_team_position", "nfl_team", "position"),
        {"schema": "sleeper"},
    )

    sleeper_player_id: Mapped[str] = mapped_column(Text, primary_key=True)
    full_name: Mapped[str | None] = mapped_column(Text)
    position: Mapped[str | None] = mapped_column(Text)
    nfl_team: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool | None]
    status: Mapped[str | None] = mapped_column(Text)
    injury_status: Mapped[str | None] = mapped_column(Text)
    age: Mapped[int | None] = mapped_column(SmallInteger)
    years_experience: Mapped[int | None] = mapped_column(SmallInteger)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)
    source_api_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sleeper.api_requests.id", ondelete="RESTRICT")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Roster(Base):
    __tablename__ = "rosters"
    __table_args__ = (
        ForeignKeyConstraint(
            ["season_roster_id", "competition_season_id"],
            ["core.season_rosters.id", "core.season_rosters.competition_season_id"],
            name="fk_rosters_season_roster_scope",
            ondelete="RESTRICT",
        ),
        Index("ix_rosters_competition_season", "competition_season_id"),
        {"schema": "sleeper"},
    )

    season_roster_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    competition_season_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    source_api_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sleeper.api_requests.id", ondelete="RESTRICT")
    )
    settings_json: Mapped[dict[str, Any]] = mapped_column("settings", JSONB)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)
    record_string: Mapped[str | None] = mapped_column(Text)
    wins: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    losses: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    ties: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    points_for: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    points_against: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RosterManager(Base):
    __tablename__ = "roster_managers"
    __table_args__ = (
        Index(
            "uq_roster_managers_one_owner",
            "season_roster_id",
            unique=True,
            postgresql_where=text("role = 'owner'"),
        ),
        Index("ix_roster_managers_user", "sleeper_user_id"),
        {"schema": "sleeper"},
    )

    season_roster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sleeper.rosters.season_roster_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    sleeper_user_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("sleeper.users.sleeper_user_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(Text)
    source_order: Mapped[int] = mapped_column(SmallInteger)
    source_api_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sleeper.api_requests.id", ondelete="RESTRICT")
    )


class RosterPlayer(Base):
    __tablename__ = "roster_players"
    __table_args__ = (
        Index("ix_roster_players_player", "sleeper_player_id"),
        {"schema": "sleeper"},
    )

    season_roster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sleeper.rosters.season_roster_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    sleeper_player_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("sleeper.players.sleeper_player_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(Text)
    source_api_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sleeper.api_requests.id", ondelete="RESTRICT")
    )


class Matchup(Base):
    __tablename__ = "matchups"
    __table_args__ = (
        ForeignKeyConstraint(
            ["season_roster_id", "competition_season_id"],
            ["core.season_rosters.id", "core.season_rosters.competition_season_id"],
            name="fk_matchups_season_roster_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "competition_season_id",
            "week",
            "season_roster_id",
            name="uq_matchups_season_week_roster",
        ),
        Index("ix_matchups_season_week_matchup", "competition_season_id", "week", "sleeper_matchup_id"),
        {"schema": "sleeper"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    competition_season_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    week: Mapped[int] = mapped_column(SmallInteger)
    season_roster_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    sleeper_matchup_id: Mapped[int | None] = mapped_column(Integer)
    points: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    source_api_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sleeper.api_requests.id", ondelete="RESTRICT")
    )


class PlayerPerformance(Base):
    __tablename__ = "player_performances"
    __table_args__ = (
        ForeignKeyConstraint(
            ["season_roster_id", "competition_season_id"],
            ["core.season_rosters.id", "core.season_rosters.competition_season_id"],
            name="fk_player_performances_roster_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "competition_season_id",
            "week",
            "season_roster_id",
            "sleeper_player_id",
            name="uq_player_performances_natural",
        ),
        Index(
            "ix_player_performances_player_season_week",
            "sleeper_player_id",
            "competition_season_id",
            "week",
        ),
        Index(
            "ix_player_performances_roster_week",
            "season_roster_id",
            "week",
        ),
        {"schema": "sleeper"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    competition_season_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    week: Mapped[int] = mapped_column(SmallInteger)
    season_roster_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    sleeper_matchup_id: Mapped[int | None] = mapped_column(Integer)
    sleeper_player_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sleeper.players.sleeper_player_id", ondelete="RESTRICT")
    )
    points: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    role: Mapped[str] = mapped_column(Text)
    source_api_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sleeper.api_requests.id", ondelete="RESTRICT")
    )


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint(
            "competition_season_id",
            "sleeper_transaction_id",
            name="uq_transactions_season_sleeper_id",
        ),
        UniqueConstraint(
            "id", "competition_season_id", name="uq_transactions_id_season"
        ),
        Index(
            "ix_transactions_season_week_type_status",
            "competition_season_id",
            "week",
            "transaction_type",
            "status",
        ),
        Index("ix_transactions_sleeper_id", "sleeper_transaction_id"),
        {"schema": "sleeper"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    competition_season_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.competition_seasons.id", ondelete="RESTRICT"),
    )
    sleeper_transaction_id: Mapped[str] = mapped_column(Text)
    week: Mapped[int] = mapped_column(SmallInteger)
    transaction_type: Mapped[str] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    provider_created_at_ms: Mapped[int | None] = mapped_column(BigInteger)
    settings_json: Mapped[dict[str, Any]] = mapped_column("settings", JSONB)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)
    source_api_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sleeper.api_requests.id", ondelete="RESTRICT")
    )


class DraftPick(Base):
    __tablename__ = "draft_picks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["original_franchise_id", "competition_id"],
            ["core.franchises.id", "core.franchises.competition_id"],
            name="fk_draft_picks_original_franchise_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["current_franchise_id", "competition_id"],
            ["core.franchises.id", "core.franchises.competition_id"],
            name="fk_draft_picks_current_franchise_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "competition_id",
            "draft_season_year",
            "round",
            "original_franchise_id",
            name="uq_draft_picks_natural",
        ),
        UniqueConstraint("id", "competition_id", name="uq_draft_picks_id_competition"),
        Index(
            "ix_draft_picks_current_owner",
            "competition_id",
            "draft_season_year",
            "current_franchise_id",
        ),
        {"schema": "sleeper"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    competition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("core.competitions.id", ondelete="RESTRICT")
    )
    draft_season_year: Mapped[int] = mapped_column(Integer)
    round: Mapped[int] = mapped_column(SmallInteger)
    original_franchise_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    current_franchise_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    sleeper_pick_id: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    source_api_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sleeper.api_requests.id", ondelete="RESTRICT")
    )


class TransactionMove(Base):
    __tablename__ = "transaction_moves"
    __table_args__ = (
        ForeignKeyConstraint(
            ["transaction_id", "competition_season_id"],
            ["sleeper.transactions.id", "sleeper.transactions.competition_season_id"],
            name="fk_transaction_moves_transaction_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["from_season_roster_id", "competition_season_id"],
            ["core.season_rosters.id", "core.season_rosters.competition_season_id"],
            name="fk_transaction_moves_from_roster_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["to_season_roster_id", "competition_season_id"],
            ["core.season_rosters.id", "core.season_rosters.competition_season_id"],
            name="fk_transaction_moves_to_roster_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "transaction_id", "move_index", name="uq_transaction_moves_index"
        ),
        Index("ix_transaction_moves_player", "sleeper_player_id"),
        Index("ix_transaction_moves_pick", "draft_pick_id"),
        Index("ix_transaction_moves_from_roster", "from_season_roster_id"),
        Index("ix_transaction_moves_to_roster", "to_season_roster_id"),
        {"schema": "sleeper"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    competition_season_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    move_index: Mapped[int] = mapped_column(Integer)
    move_kind: Mapped[str] = mapped_column(Text)
    from_season_roster_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    to_season_roster_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    sleeper_player_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("sleeper.players.sleeper_player_id", ondelete="RESTRICT")
    )
    draft_pick_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sleeper.draft_picks.id", ondelete="RESTRICT")
    )
    budget_amount: Mapped[int | None] = mapped_column(BigInteger)


class PlayoffMatchup(Base):
    __tablename__ = "playoff_matchups"
    __table_args__ = (
        ForeignKeyConstraint(
            ["t1_season_roster_id", "competition_season_id"],
            ["core.season_rosters.id", "core.season_rosters.competition_season_id"],
            name="fk_playoff_matchups_t1_roster_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["t2_season_roster_id", "competition_season_id"],
            ["core.season_rosters.id", "core.season_rosters.competition_season_id"],
            name="fk_playoff_matchups_t2_roster_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["winner_season_roster_id", "competition_season_id"],
            ["core.season_rosters.id", "core.season_rosters.competition_season_id"],
            name="fk_playoff_matchups_winner_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["loser_season_roster_id", "competition_season_id"],
            ["core.season_rosters.id", "core.season_rosters.competition_season_id"],
            name="fk_playoff_matchups_loser_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "competition_season_id",
            "bracket_kind",
            "node_key",
            name="uq_playoff_matchups_natural",
        ),
        Index(
            "ix_playoff_matchups_bracket_round",
            "competition_season_id",
            "bracket_kind",
            "round",
        ),
        Index("ix_playoff_matchups_winner", "winner_season_roster_id"),
        {"schema": "sleeper"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    competition_season_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("core.competition_seasons.id", ondelete="RESTRICT")
    )
    bracket_kind: Mapped[str] = mapped_column(Text)
    node_key: Mapped[str] = mapped_column(Text)
    round: Mapped[int] = mapped_column(SmallInteger)
    t1_season_roster_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    t2_season_roster_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    t1_from_node_key: Mapped[str | None] = mapped_column(Text)
    t1_from_outcome: Mapped[str | None] = mapped_column(Text)
    t2_from_node_key: Mapped[str | None] = mapped_column(Text)
    t2_from_outcome: Mapped[str | None] = mapped_column(Text)
    winner_season_roster_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    loser_season_roster_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    placement: Mapped[int | None] = mapped_column(SmallInteger)
    source_api_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sleeper.api_requests.id", ondelete="RESTRICT")
    )
