"""Tests for resilient completion retry and model fallback."""

from __future__ import annotations

from typing import Any

import pytest

from backend.services.reporter.runner.completion import (
    CompletionClient,
    CompletionSettings,
    RetryPolicy,
    is_retryable_error,
    retry_delay_seconds,
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


def make_client(
    complete: SequenceCompletion,
    *,
    model: str | None = None,
    fallback_models: tuple[str, ...] = (),
    retry: RetryPolicy | None = None,
) -> CompletionClient:
    return CompletionClient(
        complete,
        CompletionSettings(
            model=model,
            fallback_models=fallback_models,
            retry=retry or RetryPolicy(),
        ),
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
