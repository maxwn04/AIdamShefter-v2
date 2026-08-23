from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.resources.reporting.ai_calls import (
    BeginAICall,
    FinishAICall,
    TokenUsage,
)


def test_begin_contract_requires_positive_turns_and_json_payloads() -> None:
    command = BeginAICall(
        generation_id=uuid4(),
        turn_number=1,
        requested_model="test-model",
        input_messages=({"role": "user", "content": "hello"},),
        tool_definitions=(),
        request_parameters={"temperature": 0.2},
    )
    assert command.turn_number == 1
    with pytest.raises(ValidationError):
        BeginAICall.model_validate(
            {**command.model_dump(), "turn_number": 0}
        )


def test_finish_contract_preserves_missing_usage_and_validates_success() -> None:
    usage = TokenUsage(input_tokens=12, raw_provider_usage={"prompt_tokens": 12})
    assert usage.cached_input_tokens is None
    command = FinishAICall(
        ai_call_id=uuid4(),
        status="succeeded",
        actual_model="actual-model",
        provider_response={"choices": []},
        usage=usage,
    )
    assert command.usage.total_tokens is None
    with pytest.raises(ValidationError, match="requires actual_model"):
        FinishAICall(ai_call_id=uuid4(), status="succeeded")
    with pytest.raises(ValidationError):
        TokenUsage(input_tokens=-1)
