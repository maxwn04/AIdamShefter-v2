"""Column types that have identical semantics across all namespaces."""

from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import mapped_column

UUIDPrimaryKey = Annotated[
    UUID,
    mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    ),
]

CreatedAt = Annotated[
    datetime,
    mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
]
