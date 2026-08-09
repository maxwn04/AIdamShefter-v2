from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class Competition(Base):
    __tablename__ = "competitions"
    __table_args__ = ({"schema": "core"},)

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
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


class CompetitionSeason(Base):
    __tablename__ = "competition_seasons"
    __table_args__ = (
        UniqueConstraint(
            "competition_id",
            "season_year",
            name="uq_competition_seasons_competition_id_season_year",
        ),
        UniqueConstraint(
            "competition_id",
            "sequence_number",
            name="uq_competition_seasons_competition_id_sequence_number",
        ),
        UniqueConstraint(
            "id",
            "competition_id",
            name="uq_competition_seasons_id_competition_id",
        ),
        UniqueConstraint(
            "sleeper_league_id",
            name="uq_competition_seasons_sleeper_league_id",
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
            name="fk_competition_seasons_competition_id_competitions",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    season_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sequence_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sleeper_league_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
