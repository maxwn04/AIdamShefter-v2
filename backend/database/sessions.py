"""Explicit, short-lived SQLAlchemy session boundaries."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

SessionFactory = sessionmaker[Session]


def create_session_factory(engine: Engine) -> SessionFactory:
    """Create the one immutable session factory associated with an engine."""

    return sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


@contextmanager
def transaction_session(factory: SessionFactory) -> Iterator[Session]:
    """Yield a session in a transaction that commits or rolls back atomically."""

    with factory.begin() as session:
        yield session


@contextmanager
def read_only_session(factory: SessionFactory) -> Iterator[Session]:
    """Yield a PostgreSQL-enforced read-only transaction."""

    with factory.begin() as session:
        _ = session.execute(text("SET TRANSACTION READ ONLY"))
        yield session
