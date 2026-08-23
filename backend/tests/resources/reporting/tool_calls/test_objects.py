from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.resources.reporting.tool_calls import (
    BeginToolCall,
    FinishToolCall,
)


def test_begin_contract_validates_provider_ordinal() -> None:
    command = BeginToolCall(
        generation_id=uuid4(),
        ai_call_id=uuid4(),
        tool_ordinal=0,
        tool_name="lookup",
        implementation_version="v1",
        arguments={"week": 8},
    )
    assert command.tool_ordinal == 0
    with pytest.raises(ValidationError):
        BeginToolCall.model_validate(
            {**command.model_dump(), "tool_ordinal": -1}
        )


def test_finish_contract_requires_full_results_for_completed_calls() -> None:
    completed = FinishToolCall(
        tool_call_id=uuid4(),
        status="failed",
        full_result_text='{"ok": false}',
        error_text="unknown tool",
        error={"type": "unknown_tool"},
    )
    assert completed.error_text == "unknown tool"
    with pytest.raises(ValidationError, match="full result"):
        FinishToolCall(tool_call_id=uuid4(), status="failed")
    with pytest.raises(ValidationError, match="cannot include an error"):
        FinishToolCall(
            tool_call_id=uuid4(),
            status="succeeded",
            full_result_text="ok",
            error_text="unexpected",
        )
