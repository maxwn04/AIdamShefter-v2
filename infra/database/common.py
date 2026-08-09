"""Shared verified-connection helpers for operator-only database checks."""

import os
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool


def required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def create_verified_engine(url_environment: str, application_name: str) -> Engine:
    """Create a one-connection engine with mandatory full TLS verification."""

    database_url = required_environment(url_environment)
    url = make_url(database_url)
    if url.drivername != "postgresql+psycopg":
        raise RuntimeError(f"{url_environment} must use postgresql+psycopg")

    ca_file = Path(required_environment("AIDAM_DATABASE_CA_FILE"))
    if not ca_file.is_file():
        raise RuntimeError("AIDAM_DATABASE_CA_FILE does not exist")

    return create_engine(
        database_url,
        poolclass=NullPool,
        connect_args={
            "application_name": application_name,
            "connect_timeout": 10,
            "sslmode": "verify-full",
            "sslrootcert": str(ca_file),
        },
    )
