"""Declarative base shared by every AIdam database namespace."""

from typing import ClassVar, Final

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

APPLICATION_SCHEMAS: Final[tuple[str, ...]] = (
    "core",
    "sleeper",
    "memory",
    "reporting",
)

NAMING_CONVENTION: Final[dict[str, str]] = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base for the single metadata graph consumed by Alembic."""

    metadata: ClassVar[MetaData] = MetaData(naming_convention=NAMING_CONVENTION)
