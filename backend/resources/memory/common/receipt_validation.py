"""Competition-scoped validation for typed reporting and Sleeper receipts."""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.database.models.core import CompetitionSeason
from backend.database.models.reporting import Generation, ToolCall
from backend.database.models.sleeper import ApiRequest
from backend.resources.memory.common.errors import (
    CrossCompetitionEntityReferenceError,
    EntityReferenceNotFoundError,
)


def validate_tool_receipt(
    session: Session,
    competition_id: UUID,
    tool_call_id: UUID | None,
) -> UUID | None:
    """Validate a tool-call receipt and return its owning generation ID."""

    if tool_call_id is None:
        return None
    row = session.execute(
        sa.select(ToolCall.generation_id, Generation.competition_id)
        .join(Generation, Generation.id == ToolCall.generation_id)
        .where(ToolCall.id == tool_call_id)
    ).one_or_none()
    if row is None:
        raise EntityReferenceNotFoundError("tool_call", tool_call_id)
    generation_id, actual_scope = row
    if actual_scope != competition_id:
        raise CrossCompetitionEntityReferenceError(
            "tool_call", tool_call_id, competition_id
        )
    return generation_id


def validate_api_receipt(
    session: Session,
    competition_id: UUID,
    api_request_id: UUID | None,
) -> None:
    """Validate an API-request receipt when its request has competition scope."""

    if api_request_id is None:
        return
    row = session.execute(
        sa.select(ApiRequest.id, CompetitionSeason.competition_id)
        .outerjoin(
            CompetitionSeason,
            CompetitionSeason.id == ApiRequest.competition_season_id,
        )
        .where(ApiRequest.id == api_request_id)
    ).one_or_none()
    if row is None:
        raise EntityReferenceNotFoundError("api_request", api_request_id)
    _, actual_scope = row
    if actual_scope is not None and actual_scope != competition_id:
        raise CrossCompetitionEntityReferenceError(
            "api_request", api_request_id, competition_id
        )
