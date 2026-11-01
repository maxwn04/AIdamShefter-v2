"""Tests for provider usage normalization and durable-payload sanitization."""

from __future__ import annotations

from typing import Any

from backend.services.reporter.runner.provider_telemetry import (
    normalize_token_usage,
    sanitize_provider_error,
    sanitize_provider_response,
)


def test_token_normalization_preserves_zero_and_missing_categories() -> None:
    usage = normalize_token_usage(
        {
            "usage": {
                "input_tokens": 0,
                "output_tokens": 4,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            }
        }
    )

    assert usage.input_tokens == 0
    assert usage.cached_input_tokens == 0
    assert usage.output_tokens == 4
    assert usage.reasoning_tokens == 0
    assert usage.total_tokens is None
    assert normalize_token_usage({}).raw_provider_usage is None


def test_error_sanitizer_keeps_only_bounded_scalar_metadata() -> None:
    class ProviderError(Exception):
        status_code = 429

    error = ProviderError("Bearer top-secret " + ("x" * 3000))
    error.code = "rate_limit"
    error.request_id = "request-7"
    error.headers = {"authorization": "secret"}

    sanitized = sanitize_provider_error(error, "openai")

    assert sanitized["type"] == "ProviderError"
    assert sanitized["status_code"] == 429
    assert sanitized["code"] == "rate_limit"
    assert sanitized["request_id"] == "request-7"
    assert sanitized["provider"] == "openai"
    assert "top-secret" not in sanitized["message"]
    assert len(sanitized["message"]) == 2000
    assert "headers" not in sanitized


def test_response_sanitizer_falls_back_when_provider_dump_fails() -> None:
    class BrokenDump:
        visible = "kept"

        def __init__(self) -> None:
            self.payload = {"api_key": "secret", "value": 7}

        def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("provider serializer failed")

    sanitized = sanitize_provider_response(BrokenDump())

    assert sanitized == {
        "payload": {"api_key": "[REDACTED]", "value": 7}
    }


def test_deepseek_cache_and_reasoning_are_subsets_of_reported_totals() -> None:
    raw = {
        "prompt_tokens": 1000,
        "prompt_cache_hit_tokens": 800,
        "prompt_cache_miss_tokens": 200,
        "completion_tokens": 100,
        "completion_tokens_details": {"reasoning_tokens": 80},
        "total_tokens": 1100,
    }
    usage = normalize_token_usage({"usage": raw})

    assert usage.input_tokens == 1000
    assert usage.cached_input_tokens == 800
    assert usage.output_tokens == 100
    assert usage.reasoning_tokens == 80
    assert usage.total_tokens == 1100
    assert usage.raw_provider_usage == raw


def test_explicit_zero_cached_tokens_takes_precedence_over_provider_fallback() -> None:
    usage = normalize_token_usage({"usage": {
        "prompt_tokens_details": {"cached_tokens": 0},
        "prompt_cache_hit_tokens": 800,
    }})

    assert usage.cached_input_tokens == 0
