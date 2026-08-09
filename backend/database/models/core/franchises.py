from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class Franchise(Base):
    __tablename__ = "franchises"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "competition_id",
            name="uq_franchises_id_competition_id",
        ),
        Index(
            "ix_franchises_competition_id_archived_at",
            "competition_id",
            "archived_at",
        ),
        {"schema": "core"},
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    competition_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "core.competitions.id",
            name="fk_franchises_competition_id_competitions",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class SeasonRoster(Base):
    __tablename__ = "season_rosters"
    __table_args__ = (
        UniqueConstraint(
            "competition_season_id",
            "sleeper_roster_id",
            name="uq_season_rosters_competition_season_id_sleeper_roster_id",
        ),
        UniqueConstraint(
            "competition_season_id",
            "franchise_id",
            name="uq_season_rosters_competition_season_id_franchise_id",
        ),
        UniqueConstraint(
            "id",
            "competition_season_id",
            name="uq_season_rosters_id_competition_season_id",
        ),
        UniqueConstraint(
            "id",
            "competition_id",
            name="uq_season_rosters_id_competition_id",
        ),
        ForeignKeyConstraint(
            ["competition_season_id", "competition_id"],
            [
                "core.competition_seasons.id",
                "core.competition_seasons.competition_id",
            ],
            name="fk_season_rosters_season_competition_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["franchise_id", "competition_id"],
            ["core.franchises.id", "core.franchises.competition_id"],
            name="fk_season_rosters_franchise_competition_scope",
            ondelete="RESTRICT",
        ),
        Index("ix_season_rosters_competition_id", "competition_id"),
        Index(
            "ix_season_rosters_season_competition_scope",
            "competition_season_id",
            "competition_id",
        ),
        Index(
            "ix_season_rosters_franchise_competition_scope",
            "franchise_id",
            "competition_id",
        ),
        {"schema": "core"},
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    competition_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "core.competitions.id",
            name="fk_season_rosters_competition_id_competitions",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    competition_season_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    franchise_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    sleeper_roster_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
