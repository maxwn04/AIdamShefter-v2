"""Competition-scoped lifecycle manager for model-provider attempts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database.models.reporting import AICall as StoredAICall
from backend.database.models.reporting import Generation as StoredGeneration
from backend.database.sessions import (
    SessionFactory,
    read_only_session,
    transaction_session,
)
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.reporting.ai_calls.errors import (
    AICallConcurrencyConflict,
    AICallLifecycleConflict,
    AICallResourceNotFound,
)
from backend.resources.reporting.ai_calls.objects import (
    AICall,
    AICallPage,
    AICallQuery,
    AICallStatus,
    AICallSummary,
    BeginAICall,
    FinishAICall,
    TokenUsage,
)


class AICallManager:
    """Own retry-attempt allocation, completion, and scoped reads."""

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

    def begin_ai_call(self, command: BeginAICall) -> AICall:
        try:
            with transaction_session(self._session_factory) as session:
                generation = self._load_generation(
                    session, command.generation_id, lock=True
                )
                if generation.status != "running":
                    raise AICallLifecycleConflict(
                        generation.id,
                        "AI calls can begin only for a running generation",
                        actual_status=generation.status,
                    )
                latest_attempt = session.scalar(
                    sa.select(sa.func.max(StoredAICall.attempt_number)).where(
                        StoredAICall.generation_id == generation.id,
                        StoredAICall.turn_number == command.turn_number,
                    )
                )
                stored = StoredAICall(
                    id=uuid4(),
                    generation_id=generation.id,
                    turn_number=command.turn_number,
                    attempt_number=(
                        (latest_attempt + 1) if latest_attempt is not None else 0
                    ),
                    requested_provider=command.requested_provider,
                    requested_model=command.requested_model,
                    input_messages=list(command.input_messages),
                    tool_definitions=list(command.tool_definitions),
                    request_parameters=command.request_parameters,
                    status=AICallStatus.STARTED.value,
                )
                session.add(stored)
                session.flush()
                return _decode(stored)
        except IntegrityError:
            raise AICallConcurrencyConflict(
                "AI-call attempt identity is already allocated"
            ) from None

    def finish_ai_call(self, command: FinishAICall) -> AICall:
        try:
            with transaction_session(self._session_factory) as session:
                stored = self._load(session, command.ai_call_id, lock=True)
                if stored.status != AICallStatus.STARTED.value:
                    raise AICallLifecycleConflict(
                        stored.id,
                        "only a started AI call can be finished",
                        actual_status=stored.status,
                    )
                now = datetime.now(UTC)
                stored.status = command.status.value
                stored.actual_provider = command.actual_provider
                stored.actual_model = command.actual_model
                stored.provider_response = command.provider_response
                stored.error_jsonb = command.error
                stored.finish_reason = command.finish_reason
                stored.provider_request_id = command.provider_request_id
                stored.provider_response_id = command.provider_response_id
                stored.input_tokens = command.usage.input_tokens
                stored.cached_input_tokens = command.usage.cached_input_tokens
                stored.output_tokens = command.usage.output_tokens
                stored.reasoning_tokens = command.usage.reasoning_tokens
                stored.total_tokens = command.usage.total_tokens
                stored.raw_provider_usage = command.usage.raw_provider_usage
                stored.completed_at = now
                stored.latency_ms = max(
                    0, int((now - stored.started_at).total_seconds() * 1000)
                )
                session.flush()
                return _decode(stored)
        except IntegrityError:
            raise AICallConcurrencyConflict(
                "a successful AI call is already recorded for this turn"
            ) from None

    def get(self, ai_call_id: UUID) -> AICall:
        with read_only_session(self._session_factory) as session:
            return _decode(self._load(session, ai_call_id))

    def list(self, query: AICallQuery) -> AICallPage:
        with read_only_session(self._session_factory) as session:
            self._load_generation(session, query.generation_id)
            conditions: list[sa.ColumnElement[bool]] = [
                StoredAICall.generation_id == query.generation_id
            ]
            if query.turn_number is not None:
                conditions.append(StoredAICall.turn_number == query.turn_number)
            if query.status is not None:
                conditions.append(StoredAICall.status == query.status.value)
            total = cast(
                int,
                session.scalar(
                    sa.select(sa.func.count())
                    .select_from(StoredAICall)
                    .where(*conditions)
                ),
            )
            rows = session.scalars(
                sa.select(StoredAICall)
                .where(*conditions)
                .order_by(
                    StoredAICall.turn_number.asc(),
                    StoredAICall.attempt_number.asc(),
                )
                .limit(query.limit)
                .offset(query.offset)
            ).all()
            return AICallPage(
                items=tuple(_decode_summary(row) for row in rows),
                total=total,
                limit=query.limit,
                offset=query.offset,
            )

    def _load(
        self,
        session: Session,
        ai_call_id: UUID,
        *,
        lock: bool = False,
    ) -> StoredAICall:
        statement = (
            sa.select(StoredAICall)
            .join(StoredGeneration, StoredGeneration.id == StoredAICall.generation_id)
            .where(
                StoredAICall.id == ai_call_id,
                StoredGeneration.competition_id == self._competition_id,
            )
        )
        if lock:
            statement = statement.with_for_update(of=StoredAICall)
        stored = session.scalar(statement)
        if stored is None:
            raise AICallResourceNotFound("ai_call", ai_call_id)
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
            raise AICallResourceNotFound("generation", generation_id)
        return stored


def _usage(stored: StoredAICall) -> TokenUsage:
    return TokenUsage(
        input_tokens=stored.input_tokens,
        cached_input_tokens=stored.cached_input_tokens,
        output_tokens=stored.output_tokens,
        reasoning_tokens=stored.reasoning_tokens,
        total_tokens=stored.total_tokens,
        raw_provider_usage=stored.raw_provider_usage,
    )


def _decode(stored: StoredAICall) -> AICall:
    return AICall(
        id=stored.id,
        generation_id=stored.generation_id,
        turn_number=stored.turn_number,
        attempt_number=stored.attempt_number,
        requested_provider=stored.requested_provider,
        requested_model=stored.requested_model,
        actual_provider=stored.actual_provider,
        actual_model=stored.actual_model,
        input_messages=tuple(stored.input_messages),
        tool_definitions=tuple(stored.tool_definitions),
        request_parameters=stored.request_parameters,
        provider_response=stored.provider_response,
        status=stored.status,
        error=stored.error_jsonb,
        finish_reason=stored.finish_reason,
        provider_request_id=stored.provider_request_id,
        provider_response_id=stored.provider_response_id,
        usage=_usage(stored),
        started_at=stored.started_at,
        completed_at=stored.completed_at,
        latency_ms=stored.latency_ms,
    )


def _decode_summary(stored: StoredAICall) -> AICallSummary:
    return AICallSummary(
        id=stored.id,
        generation_id=stored.generation_id,
        turn_number=stored.turn_number,
        attempt_number=stored.attempt_number,
        requested_provider=stored.requested_provider,
        requested_model=stored.requested_model,
        actual_provider=stored.actual_provider,
        actual_model=stored.actual_model,
        status=stored.status,
        finish_reason=stored.finish_reason,
        usage=_usage(stored),
        started_at=stored.started_at,
        completed_at=stored.completed_at,
        latency_ms=stored.latency_ms,
    )


__all__ = ["AICallManager"]
