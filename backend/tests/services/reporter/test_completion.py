"""Tests for resilient completion retry and model fallback."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from backend.services.reporter.generator import _resolve_client
from backend.services.reporter.runner.completion import (
    CompletionClient,
    CompletionSettings,
    RetryPolicy,
    is_retryable_error,
    retry_delay_seconds,
)
from backend.services.reporter.runner.recording import (
    ModelAttemptFinish,
    ModelAttemptStart,
)
from backend.services.reporter.runner.runner import Runner
from backend.services.reporter.runner.tools.registry import ToolRegistry
from backend.tests.services.reporter.test_runner import make_response, run


class RateLimitError(Exception):
    """Stand-in for provider rate-limit errors."""

    def __init__(self, message: str = "Rate limit exceeded", *, status_code: int = 429):
        super().__init__(message)
        self.status_code = status_code


class SequenceCompletion:
    """Completion fn that returns or raises items from a prebuilt sequence."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        if not self.outcomes:
            return make_response(text="empty")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class RecordingProbe:
    def __init__(
        self,
        *,
        fail_begin: bool = False,
        fail_finish: bool = False,
    ) -> None:
        self.fail_begin = fail_begin
        self.fail_finish = fail_finish
        self.started: list[tuple[UUID, ModelAttemptStart]] = []
        self.finished: list[tuple[UUID, ModelAttemptFinish]] = []
        self.successful: dict[int, UUID] = {}

    def begin_model_attempt(self, attempt: ModelAttemptStart) -> UUID:
        if self.fail_begin:
            raise RateLimitError("recorder timeout")
        attempt_id = uuid4()
        self.started.append((attempt_id, attempt))
        return attempt_id

    def finish_model_attempt(
        self,
        attempt_id: UUID,
        result: ModelAttemptFinish,
    ) -> None:
        if self.fail_finish:
            raise RateLimitError("recorder finish timeout")
        self.finished.append((attempt_id, result))
        if result.status == "succeeded":
            turn = next(
                attempt.turn_number
                for started_id, attempt in self.started
                if started_id == attempt_id
            )
            self.successful[turn] = attempt_id

    def successful_ai_call_id(self, turn_number: int) -> UUID | None:
        return self.successful.get(turn_number)


def make_client(
    complete: SequenceCompletion,
    *,
    model: str | None = None,
    fallback_models: tuple[str, ...] = (),
    retry: RetryPolicy | None = None,
    recorder: RecordingProbe | None = None,
) -> CompletionClient:
    return CompletionClient(
        complete,
        CompletionSettings(
            model=model,
            fallback_models=fallback_models,
            retry=retry or RetryPolicy(),
        ),
        recorder,
    )


def test_is_retryable_detects_rate_limit_by_type_and_status() -> None:
    assert is_retryable_error(RateLimitError())
    assert is_retryable_error(Exception("HTTP 429 too many requests"))
    assert not is_retryable_error(ValueError("bad request"))


def test_is_retryable_detects_empty_provider_json_response() -> None:
    class APIError(Exception):
        pass

    assert is_retryable_error(
        APIError(
            "DeepseekException - Unable to get json response - "
            "Expecting value: line 1 column 1 (char 0), Original Response: "
        )
    )
    assert not is_retryable_error(APIError("invalid api key"))


def test_requires_none_reasoning_with_tools_for_luna() -> None:
    from backend.services.reporter.runner.completion import _requires_none_reasoning_with_tools

    assert _requires_none_reasoning_with_tools("gpt-5.6-luna")
    assert _requires_none_reasoning_with_tools("openai/gpt-5.6-luna")
    assert not _requires_none_reasoning_with_tools("deepseek/deepseek-v4-pro")
    assert not _requires_none_reasoning_with_tools(None)


def test_retry_policy_validation() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        RetryPolicy(max_retries=-1)
    with pytest.raises(ValueError, match="base_delay"):
        RetryPolicy(base_delay=0)
    with pytest.raises(ValueError, match="max_delay"):
        RetryPolicy(base_delay=2.0, max_delay=1.0)


def test_completion_settings_model_chain_dedupes() -> None:
    settings = CompletionSettings(
        model="primary",
        fallback_models=("fallback", "primary", "", "other"),
    )
    assert settings.model_chain() == ("primary", "fallback", "other")
    assert CompletionSettings().model_chain() == ()


def test_retry_delay_is_bounded(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.services.reporter.runner.completion.random.uniform",
        lambda _low, high: high,
    )
    assert retry_delay_seconds(0, base_delay=1.0, max_delay=30.0) == 1.0
    assert retry_delay_seconds(5, base_delay=1.0, max_delay=30.0) == 30.0


def test_retry_delay_honors_provider_suggested_wait(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.services.reporter.runner.completion.random.uniform",
        lambda low, high: low if high >= 3 else high,
    )
    delay = retry_delay_seconds(
        0,
        base_delay=1.0,
        max_delay=30.0,
        error=RateLimitError("Please try again in 3.188s."),
    )
    assert delay >= 3.188
    assert delay <= 30.0


def test_suggested_retry_delay_parses_message() -> None:
    from backend.services.reporter.runner.completion import suggested_retry_delay_seconds

    assert suggested_retry_delay_seconds(
        RateLimitError("Please try again in 3.188s.")
    ) == 3.188
    assert suggested_retry_delay_seconds(
        RateLimitError("Please try again in 250ms")
    ) == 0.25
    assert suggested_retry_delay_seconds(ValueError("nope")) is None


def test_client_retries_same_model_then_succeeds(monkeypatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("backend.services.reporter.runner.completion.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(
        "backend.services.reporter.runner.completion.random.uniform",
        lambda _low, high: high,
    )

    complete = SequenceCompletion(
        [
            RateLimitError("429"),
            RateLimitError("429"),
            make_response(text="ok"),
        ]
    )
    client = make_client(
        complete,
        model="primary",
        retry=RetryPolicy(max_retries=3, base_delay=1.0, max_delay=30.0),
    )

    result = run(client.complete(messages=[]))

    assert result.choices[0].message.content == "ok"
    assert [req["model"] for req in complete.requests] == [
        "primary",
        "primary",
        "primary",
    ]
    assert sleeps == [1.0, 2.0]


def test_client_falls_back_after_retries(monkeypatch) -> None:
    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("backend.services.reporter.runner.completion.asyncio.sleep", fake_sleep)

    complete = SequenceCompletion(
        [
            RateLimitError("primary-1"),
            RateLimitError("primary-2"),
            RateLimitError("primary-3"),
            RateLimitError("primary-4"),
            make_response(text="fallback-ok"),
        ]
    )
    client = make_client(
        complete,
        model="primary",
        fallback_models=("fallback",),
        retry=RetryPolicy(max_retries=3, base_delay=0.01, max_delay=0.01),
    )

    result = run(client.complete(messages=[]))

    assert result.choices[0].message.content == "fallback-ok"
    models = [req["model"] for req in complete.requests]
    assert models == ["primary", "primary", "primary", "primary", "fallback"]


def test_client_raises_non_retryable_immediately() -> None:
    complete = SequenceCompletion([ValueError("invalid request")])
    client = make_client(
        complete,
        model="primary",
        fallback_models=("fallback",),
        retry=RetryPolicy(max_retries=3),
    )

    with pytest.raises(ValueError, match="invalid request"):
        run(client.complete(messages=[]))

    assert [req["model"] for req in complete.requests] == ["primary"]


def test_client_raises_after_all_models_exhausted(monkeypatch) -> None:
    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("backend.services.reporter.runner.completion.asyncio.sleep", fake_sleep)

    complete = SequenceCompletion(
        [
            RateLimitError("a1"),
            RateLimitError("a2"),
            RateLimitError("b1"),
            RateLimitError("b2"),
        ]
    )
    client = make_client(
        complete,
        model="primary",
        fallback_models=("fallback",),
        retry=RetryPolicy(max_retries=1, base_delay=0.01, max_delay=0.01),
    )

    with pytest.raises(RateLimitError, match="b2"):
        run(client.complete(messages=[]))


def test_runner_uses_fallback_model_on_rate_limits(monkeypatch) -> None:
    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("backend.services.reporter.runner.completion.asyncio.sleep", fake_sleep)

    complete = SequenceCompletion(
        [
            RateLimitError("primary down"),
            make_response(text="from fallback"),
        ]
    )
    runner = Runner(
        ToolRegistry(),
        client=make_client(
            complete,
            model="gpt-primary",
            fallback_models=("gpt-fallback",),
            retry=RetryPolicy(max_retries=0),
        ),
    )

    output = run(runner.run("system", "user"))

    assert "from fallback" in str(runner.log.entries) or output.article == ""
    assert [req["model"] for req in complete.requests] == [
        "gpt-primary",
        "gpt-fallback",
    ]


def test_recorded_success_retains_exact_response_and_normalized_usage() -> None:
    response = {
        "id": "response-1",
        "model": "actual-model",
        "provider": "openai",
        "choices": [{"finish_reason": "tool_calls", "message": {"content": None}}],
        "usage": {
            "prompt_tokens": 20,
            "completion_tokens": 8,
            "total_tokens": 28,
            "prompt_tokens_details": {"cached_tokens": 3},
            "completion_tokens_details": {"reasoning_tokens": 2},
        },
        "authorization": "Bearer provider-secret",
    }
    complete = SequenceCompletion([response])
    recorder = RecordingProbe()
    client = make_client(complete, model="openai/requested-model", recorder=recorder)

    returned = run(
        client.complete(
            turn_number=3,
            messages=[{"role": "user", "content": "hello"}],
            tools=[{"type": "function", "function": {"name": "lookup"}}],
            temperature=0.25,
        )
    )

    assert returned is response
    assert len(recorder.started) == 1
    _, started = recorder.started[0]
    assert started.turn_number == 3
    assert started.requested_provider == "openai"
    assert started.requested_model == "openai/requested-model"
    assert started.request_parameters == {"temperature": 0.25}
    _, finished = recorder.finished[0]
    assert finished.status == "succeeded"
    assert finished.actual_model == "actual-model"
    assert finished.provider_response["authorization"] == "[REDACTED]"
    assert finished.usage.input_tokens == 20
    assert finished.usage.cached_input_tokens == 3
    assert finished.usage.output_tokens == 8
    assert finished.usage.reasoning_tokens == 2
    assert finished.usage.total_tokens == 28
    assert recorder.successful_ai_call_id(3) is not None


def test_every_retry_and_fallback_is_recorded_as_its_own_attempt(monkeypatch) -> None:
    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("backend.services.reporter.runner.completion.asyncio.sleep", fake_sleep)
    complete = SequenceCompletion(
        [
            RateLimitError("primary retry"),
            RateLimitError("primary exhausted"),
            {"model": "fallback", "choices": [{"finish_reason": "stop"}]},
        ]
    )
    recorder = RecordingProbe()
    client = make_client(
        complete,
        model="primary",
        fallback_models=("fallback",),
        retry=RetryPolicy(max_retries=1, base_delay=0.01, max_delay=0.01),
        recorder=recorder,
    )

    run(client.complete(turn_number=1, messages=[]))

    assert [attempt.requested_model for _, attempt in recorder.started] == [
        "primary",
        "primary",
        "fallback",
    ]
    assert [result.status for _, result in recorder.finished] == [
        "retryable_error",
        "retryable_error",
        "succeeded",
    ]


def test_retry_exhaustion_leaves_every_attempt_terminal() -> None:
    complete = SequenceCompletion([RateLimitError("primary"), RateLimitError("fallback")])
    recorder = RecordingProbe()
    client = make_client(
        complete,
        model="primary",
        fallback_models=("fallback",),
        retry=RetryPolicy(max_retries=0),
        recorder=recorder,
    )

    with pytest.raises(RateLimitError, match="fallback"):
        run(client.complete(turn_number=1, messages=[]))

    assert len(recorder.started) == 2
    assert [result.status for _, result in recorder.finished] == [
        "retryable_error",
        "retryable_error",
    ]


def test_fatal_error_is_sanitized_and_recorded_once() -> None:
    error = ValueError("invalid api_key=super-secret Bearer bearer-secret")
    complete = SequenceCompletion([error])
    recorder = RecordingProbe()
    client = make_client(complete, model="primary", recorder=recorder)

    with pytest.raises(ValueError, match="invalid"):
        run(client.complete(turn_number=1, messages=[]))

    assert len(recorder.started) == 1
    result = recorder.finished[0][1]
    assert result.status == "fatal_error"
    assert "super-secret" not in result.error["message"]
    assert "bearer-secret" not in result.error["message"]


def test_inflight_cancellation_records_unknown_outcome() -> None:
    class CancelledCompletion:
        async def __call__(self, **_kwargs: Any) -> Any:
            raise asyncio.CancelledError("caller cancelled")

    recorder = RecordingProbe()
    client = CompletionClient(
        CancelledCompletion(),
        CompletionSettings(model="primary"),
        recorder,
    )

    with pytest.raises(asyncio.CancelledError):
        run(client.complete(turn_number=1, messages=[]))

    assert recorder.finished[0][1].status == "unknown_outcome"


def test_recorder_begin_failure_prevents_provider_call() -> None:
    complete = SequenceCompletion([{"model": "unused", "choices": []}])
    client = make_client(
        complete,
        model="primary",
        recorder=RecordingProbe(fail_begin=True),
    )

    with pytest.raises(RuntimeError, match="before provider invocation"):
        run(client.complete(turn_number=1, messages=[]))

    assert complete.requests == []


def test_recorder_finish_failure_prevents_success_from_escaping() -> None:
    response = {"model": "primary", "choices": [{"finish_reason": "stop"}]}
    complete = SequenceCompletion([response])
    client = make_client(
        complete,
        model="primary",
        recorder=RecordingProbe(fail_finish=True),
    )

    with pytest.raises(RuntimeError, match="after provider invocation"):
        run(client.complete(turn_number=1, messages=[]))

    assert len(complete.requests) == 1


def test_recording_requires_model_and_positive_turn() -> None:
    complete = SequenceCompletion([])
    recorder = RecordingProbe()

    with pytest.raises(ValueError, match="configured model"):
        run(make_client(complete, recorder=recorder).complete(turn_number=1, messages=[]))
    with pytest.raises(ValueError, match="positive turn"):
        run(
            make_client(complete, model="primary", recorder=recorder).complete(
                messages=[]
            )
        )
    assert complete.requests == []


def test_generator_client_resolution_preserves_recorder_identity() -> None:
    complete = SequenceCompletion([])
    recorder = RecordingProbe()
    resolved = _resolve_client(
        client=None,
        completion=CompletionSettings(model="primary"),
        complete=complete,
        recorder=recorder,
    )

    assert resolved.recorder is recorder
    with pytest.raises(ValueError, match="already use"):
        _resolve_client(
            client=CompletionClient(complete, CompletionSettings(model="primary")),
            completion=None,
            complete=None,
            recorder=recorder,
        )


def test_litellm_style_object_metadata_and_usage_are_recorded() -> None:
    response = SimpleNamespace(
        id="response-object",
        model="provider-model",
        choices=[SimpleNamespace(finish_reason="stop")],
        usage=SimpleNamespace(
            prompt_tokens=11,
            completion_tokens=6,
            total_tokens=17,
            prompt_tokens_details=SimpleNamespace(cached_tokens=4),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=2),
        ),
        _hidden_params={
            "custom_llm_provider": "azure",
            "additional_headers": {"X-Request-ID": "request-object"},
        },
    )
    recorder = RecordingProbe()
    client = make_client(
        SequenceCompletion([response]),
        model="openai/requested",
        recorder=recorder,
    )

    run(client.complete(turn_number=1, messages=[]))

    result = recorder.finished[0][1]
    assert result.actual_provider == "azure"
    assert result.actual_model == "provider-model"
    assert result.provider_request_id == "request-object"
    assert result.provider_response_id == "response-object"
    assert result.finish_reason == "stop"
    assert result.usage.cached_input_tokens == 4
    assert result.usage.reasoning_tokens == 2
    assert result.usage.raw_provider_usage["prompt_tokens"] == 11
