"""Tests for resilient completion retry and model fallback."""

from __future__ import annotations

from typing import Any

import pytest

from reporter_v2.runner.completion import (
    complete_with_retry,
    is_retryable_error,
    retry_delay_seconds,
)
from reporter_v2.runner.runner import Runner
from reporter_v2.runner.state import RunnerConfig
from reporter_v2.runner.tools.registry import ToolRegistry
from reporter_v2.tests.test_runner import make_response, run


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


def test_retry_delay_is_bounded(monkeypatch) -> None:
    monkeypatch.setattr(
        "reporter_v2.runner.completion.random.uniform",
        lambda _low, high: high,
    )
    assert retry_delay_seconds(0, base_delay=1.0, max_delay=30.0) == 1.0
    assert retry_delay_seconds(5, base_delay=1.0, max_delay=30.0) == 30.0


def test_complete_with_retry_retries_same_model_then_succeeds(monkeypatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("reporter_v2.runner.completion.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(
        "reporter_v2.runner.completion.random.uniform",
        lambda _low, high: high,
    )

    complete = SequenceCompletion(
        [
            RateLimitError("429"),
            RateLimitError("429"),
            make_response(text="ok"),
        ]
    )

    result = run(
        complete_with_retry(
            complete,
            model="primary",
            max_retries=3,
            retry_base_delay=1.0,
            retry_max_delay=30.0,
            messages=[],
        )
    )

    assert result.choices[0].message.content == "ok"
    assert [req["model"] for req in complete.requests] == [
        "primary",
        "primary",
        "primary",
    ]
    assert sleeps == [1.0, 2.0]


def test_complete_with_retry_falls_back_after_retries(monkeypatch) -> None:
    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("reporter_v2.runner.completion.asyncio.sleep", fake_sleep)

    complete = SequenceCompletion(
        [
            RateLimitError("primary-1"),
            RateLimitError("primary-2"),
            RateLimitError("primary-3"),
            RateLimitError("primary-4"),
            make_response(text="fallback-ok"),
        ]
    )

    result = run(
        complete_with_retry(
            complete,
            model="primary",
            fallback_models=["fallback"],
            max_retries=3,
            retry_base_delay=0.01,
            retry_max_delay=0.01,
            messages=[],
        )
    )

    assert result.choices[0].message.content == "fallback-ok"
    models = [req["model"] for req in complete.requests]
    assert models == ["primary", "primary", "primary", "primary", "fallback"]


def test_complete_with_retry_raises_non_retryable_immediately() -> None:
    complete = SequenceCompletion([ValueError("invalid request")])

    with pytest.raises(ValueError, match="invalid request"):
        run(
            complete_with_retry(
                complete,
                model="primary",
                fallback_models=["fallback"],
                max_retries=3,
                messages=[],
            )
        )

    assert [req["model"] for req in complete.requests] == ["primary"]


def test_complete_with_retry_raises_after_all_models_exhausted(monkeypatch) -> None:
    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("reporter_v2.runner.completion.asyncio.sleep", fake_sleep)

    complete = SequenceCompletion(
        [
            RateLimitError("a1"),
            RateLimitError("a2"),
            RateLimitError("b1"),
            RateLimitError("b2"),
        ]
    )

    with pytest.raises(RateLimitError, match="b2"):
        run(
            complete_with_retry(
                complete,
                model="primary",
                fallback_models=["fallback"],
                max_retries=1,
                retry_base_delay=0.01,
                retry_max_delay=0.01,
                messages=[],
            )
        )


def test_runner_uses_fallback_model_on_rate_limits(monkeypatch) -> None:
    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("reporter_v2.runner.completion.asyncio.sleep", fake_sleep)

    complete = SequenceCompletion(
        [
            RateLimitError("primary down"),
            make_response(text="from fallback"),
        ]
    )
    runner = Runner(
        ToolRegistry(),
        complete=complete,
        config=RunnerConfig(
            model="gpt-primary",
            fallback_models=["gpt-fallback"],
            max_retries=0,
        ),
    )

    output = run(runner.run("system", "user"))

    assert "from fallback" in str(runner.log.entries) or output.article == ""
    assert [req["model"] for req in complete.requests] == [
        "gpt-primary",
        "gpt-fallback",
    ]
