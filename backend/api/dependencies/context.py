"""Request-bound resource manager context construction."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Header

from backend.resources.context import ActorKind, ManagerContext


def get_competition_manager_context(
    competition_id: UUID,
    request_id: Annotated[
        str | None,
        Header(alias="X-Request-ID", max_length=128),
    ] = None,
) -> ManagerContext:
    """Build the manager scope for a competition-bound API operation."""

    correlation_id = request_id.strip() if request_id else None
    return ManagerContext.competition(
        actor_kind=ActorKind.API,
        actor_id="local-api",
        competition_id=competition_id,
        correlation_id=correlation_id or str(uuid4()),
    )
