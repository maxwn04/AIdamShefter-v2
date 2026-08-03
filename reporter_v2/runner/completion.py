"""Resilient LiteLLM completion with retry and model fallback."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any

CompletionFn = Callable[..., Awaitable[Any]]

logger = logging.getLogger(__name__)

# Exception type names from litellm / openai / httpx that are worth retrying.
_RETRYABLE_TYPE_NAMES = frozenset(
    {
        "RateLimitError",
        "ServiceUnavailableError",
        "APIConnectionError",
        "APITimeoutError",
        "Timeout",
        "InternalServerError",
        "BadGatewayError",
        "GatewayTimeoutError",
    }
)

_RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

_RETRYABLE_MESSAGE_FRAGMENTS = (
    "rate limit",
    "rate_limit",
    "ratelimit",
    "too many requests",
    "overloaded",
    "temporarily unavailable",
    "timeout",
    "timed out",
    "connection reset",
    "connection aborted",
    "unable to get json response",
    "expecting value",
    "jsondecodeerror",
    "empty response",
    "503",
    "502",
    "504",
    "429",
)


def is_retryable_error(exc: BaseException) -> bool:
    """Return True when the error looks transient / rate-limited."""
    type_name = type(exc).__name__
    if type_name in _RETRYABLE_TYPE_NAMES:
        return True

    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(exc, "status", None)
    if status in _RETRYABLE_STATUS_CODES:
        return True

    response = getattr(exc, "response", None)
    if response is not None:
        response_status = getattr(response, "status_code", None)
        if response_status in _RETRYABLE_STATUS_CODES:
            return True

    message = str(exc).lower()
    return any(fragment in message for fragment in _RETRYABLE_MESSAGE_FRAGMENTS)


def retry_delay_seconds(
    attempt: int,
    *,
    base_delay: float,
    max_delay: float,
) -> float:
    """Exponential backoff with full jitter for retry attempt N (0-indexed)."""
    ceiling = min(max_delay, base_delay * (2**attempt))
    return random.uniform(0, ceiling)


async def complete_with_retry(
    complete: CompletionFn,
    *,
    model: str | None,
    fallback_models: list[str] | None = None,
    max_retries: int = 3,
    retry_base_delay: float = 1.0,
    retry_max_delay: float = 30.0,
    **kwargs: Any,
) -> Any:
    """Call ``complete`` with exponential retries, then model fallbacks.

    For each model in ``[model] + fallback_models``:
    1. Attempt the call.
    2. On a retryable error, wait with exponential backoff and retry up to
       ``max_retries`` additional times on the same model.
    3. If that model is exhausted, move to the next fallback model.
    4. Non-retryable errors are raised immediately.
    """
    models = _model_chain(model, fallback_models)
    if not models:
        # Preserve callers that inject fakes without configuring a model.
        return await complete(model=model, **kwargs)

    last_error: BaseException | None = None
    for model_index, candidate in enumerate(models):
        for attempt in range(max_retries + 1):
            try:
                return await complete(model=candidate, **kwargs)
            except Exception as exc:
                if not is_retryable_error(exc):
                    raise

                last_error = exc
                is_last_attempt = attempt >= max_retries
                is_last_model = model_index >= len(models) - 1

                if is_last_attempt and is_last_model:
                    break

                if is_last_attempt:
                    logger.warning(
                        "Model %s exhausted after %d retries (%s); "
                        "falling back to %s",
                        candidate,
                        max_retries,
                        exc,
                        models[model_index + 1],
                    )
                    break

                delay = retry_delay_seconds(
                    attempt,
                    base_delay=retry_base_delay,
                    max_delay=retry_max_delay,
                )
                logger.warning(
                    "Retryable error on model %s (attempt %d/%d): %s; "
                    "retrying in %.2fs",
                    candidate,
                    attempt + 1,
                    max_retries + 1,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

    assert last_error is not None
    raise last_error


def _model_chain(
    model: str | None,
    fallback_models: list[str] | None,
) -> list[str]:
    chain: list[str] = []
    seen: set[str] = set()
    for candidate in [model, *(fallback_models or [])]:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        chain.append(candidate)
    return chain


def make_litellm_completion() -> CompletionFn:
    """Return the default LiteLLM async completion function."""
    import litellm

    return litellm.acompletion
