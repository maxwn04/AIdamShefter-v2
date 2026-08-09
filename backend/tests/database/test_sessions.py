from typing import cast

from sqlalchemy import Engine, text

from backend.database.sessions import (
    create_session_factory,
    read_only_session,
    transaction_session,
)


def test_session_factory_uses_explicit_write_points(database_engine: Engine) -> None:
    factory = create_session_factory(database_engine)

    assert factory.kw["autoflush"] is False
    assert factory.kw["expire_on_commit"] is False
    with transaction_session(factory) as session:
        assert session.scalar(text("SELECT 1")) == 1


def test_read_only_session_enforces_postgresql_transaction_mode(
    database_engine: Engine,
) -> None:
    factory = create_session_factory(database_engine)

    with read_only_session(factory) as session:
        read_only = cast(
            str,
            session.scalar(text("SELECT current_setting('transaction_read_only')")),
        )

    assert read_only == "on"
