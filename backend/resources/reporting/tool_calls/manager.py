"""Competition-scoped lifecycle manager for reporter tool executions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database.models.reporting import AICall as StoredAICall
from backend.database.models.reporting import Generation as StoredGeneration
from backend.database.models.reporting import ToolCall as StoredToolCall
from backend.database.sessions import (
    SessionFactory,
    read_only_session,
    transaction_session,
)
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.reporting.tool_calls.errors import (
    ToolCallConcurrencyConflict,
    ToolCallLifecycleConflict,
    ToolCallResourceNotFound,
)
from backend.resources.reporting.tool_calls.objects import (
    BeginToolCall,
    FinishToolCall,
    ToolCall,
    ToolCallPage,
    ToolCallQuery,
    ToolCallStatus,
    ToolCallSummary,
)


class ToolCallManager:
    """Own provider ordinals, provenance validation, completion, and reads."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id

    @property
    def competition_id(self) -> UUID:
        return self._competition_id

    def begin_tool_call(self, command: BeginToolCall) -> ToolCall:
        try:
            with transaction_session(self._session_factory) as session:
                generation = self._load_generation(
                    session, command.generation_id, lock=True
                )
                if generation.status != "running":
                    raise ToolCallLifecycleConflict(
                        generation.id,
                        "tool calls can begin only for a running generation",
                        actual_status=generation.status,
                    )
                ai_call = session.scalar(
                    sa.select(StoredAICall).where(
                        StoredAICall.id == command.ai_call_id,
                        StoredAICall.generation_id == generation.id,
                    )
                )
                if ai_call is None:
                    raise ToolCallResourceNotFound("ai_call", command.ai_call_id)
                if ai_call.status != "succeeded":
                    raise ToolCallLifecycleConflict(
                        ai_call.id,
                        "tool calls require a succeeded AI call",
                        actual_status=ai_call.status,
                    )
                stored = StoredToolCall(
                    id=uuid4(),
                    generation_id=generation.id,
                    ai_call_id=ai_call.id,
                    tool_ordinal=command.tool_ordinal,
                    provider_tool_call_id=command.provider_tool_call_id,
                    tool_name=command.tool_name,
                    implementation_version=command.implementation_version,
                    arguments_jsonb=command.arguments,
                    status=ToolCallStatus.RUNNING.value,
                    started_at=datetime.now(UTC),
                )
                session.add(stored)
                session.flush()
                return _decode(stored)
        except IntegrityError:
            raise ToolCallConcurrencyConflict(
                "tool ordinal is already allocated for this AI call"
            ) from None

    def finish_tool_call(self, command: FinishToolCall) -> ToolCall:
        with transaction_session(self._session_factory) as session:
            stored = self._load(session, command.tool_call_id, lock=True)
            if stored.status != ToolCallStatus.RUNNING.value:
                raise ToolCallLifecycleConflict(
                    stored.id,
                    "only a running tool call can be finished",
                    actual_status=stored.status,
                )
            now = datetime.now(UTC)
            stored.status = command.status.value
            stored.full_result_text = command.full_result_text
            stored.structured_result_jsonb = command.structured_result
            stored.error_text = command.error_text
            stored.error_jsonb = command.error
            stored.completed_at = now
            stored.duration_ms = max(
                0, int((now - cast(datetime, stored.started_at)).total_seconds() * 1000)
            )
            session.flush()
            return _decode(stored)

    def get(self, tool_call_id: UUID) -> ToolCall:
        with read_only_session(self._session_factory) as session:
            return _decode(self._load(session, tool_call_id))

    def list(self, query: ToolCallQuery) -> ToolCallPage:
        with read_only_session(self._session_factory) as session:
            self._load_generation(session, query.generation_id)
            conditions: list[sa.ColumnElement[bool]] = [
                StoredToolCall.generation_id == query.generation_id
            ]
            if query.ai_call_id is not None:
                conditions.append(StoredToolCall.ai_call_id == query.ai_call_id)
            if query.status is not None:
                conditions.append(StoredToolCall.status == query.status.value)
            total = cast(
                int,
                session.scalar(
                    sa.select(sa.func.count())
                    .select_from(StoredToolCall)
                    .where(*conditions)
                ),
            )
            rows = session.scalars(
                sa.select(StoredToolCall)
                .where(*conditions)
                .order_by(
                    StoredToolCall.ai_call_id.asc(),
                    StoredToolCall.tool_ordinal.asc(),
                )
                .limit(query.limit)
                .offset(query.offset)
            ).all()
            return ToolCallPage(
                items=tuple(_decode_summary(row) for row in rows),
                total=total,
                limit=query.limit,
                offset=query.offset,
            )

    def _load(
        self,
        session: Session,
        tool_call_id: UUID,
        *,
        lock: bool = False,
    ) -> StoredToolCall:
        statement = (
            sa.select(StoredToolCall)
            .join(
                StoredGeneration,
                StoredGeneration.id == StoredToolCall.generation_id,
            )
            .where(
                StoredToolCall.id == tool_call_id,
                StoredGeneration.competition_id == self._competition_id,
            )
        )
        if lock:
            statement = statement.with_for_update(of=StoredToolCall)
        stored = session.scalar(statement)
        if stored is None:
            raise ToolCallResourceNotFound("tool_call", tool_call_id)
        return stored

    def _load_generation(
        self,
        session: Session,
        generation_id: UUID,
        *,
        lock: bool = False,
    ) -> StoredGeneration:
        statement = sa.select(StoredGeneration).where(
            StoredGeneration.id == generation_id,
            StoredGeneration.competition_id == self._competition_id,
        )
        if lock:
            statement = statement.with_for_update()
        stored = session.scalar(statement)
        if stored is None:
            raise ToolCallResourceNotFound("generation", generation_id)
        return stored


def _decode(stored: StoredToolCall) -> ToolCall:
    return ToolCall(
        id=stored.id,
        generation_id=stored.generation_id,
        ai_call_id=stored.ai_call_id,
        tool_ordinal=stored.tool_ordinal,
        provider_tool_call_id=stored.provider_tool_call_id,
        tool_name=stored.tool_name,
        implementation_version=stored.implementation_version,
        arguments=stored.arguments_jsonb,
        status=stored.status,
        full_result_text=stored.full_result_text,
        structured_result=stored.structured_result_jsonb,
        error_text=stored.error_text,
        error=stored.error_jsonb,
        started_at=cast(datetime, stored.started_at),
        completed_at=stored.completed_at,
        duration_ms=stored.duration_ms,
    )


def _decode_summary(stored: StoredToolCall) -> ToolCallSummary:
    return ToolCallSummary(
        id=stored.id,
        generation_id=stored.generation_id,
        ai_call_id=stored.ai_call_id,
        tool_ordinal=stored.tool_ordinal,
        provider_tool_call_id=stored.provider_tool_call_id,
        tool_name=stored.tool_name,
        implementation_version=stored.implementation_version,
        status=stored.status,
        started_at=cast(datetime, stored.started_at),
        completed_at=stored.completed_at,
        duration_ms=stored.duration_ms,
    )


__all__ = ["ToolCallManager"]
