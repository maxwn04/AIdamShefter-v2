"""Resilient LiteLLM completion with retry and model fallback."""

from __future__ import annotations

import asyncio
import logging
import random
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

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

_RETRY_AFTER_RE = re.compile(
    r"try again in\s+(\d+(?:\.\d+)?)\s*(ms|s|sec|secs|second|seconds)?",
    re.IGNORECASE,
)


class CompletionFn(Protocol):
    async def __call__(
        self,
        *,
        model: str | None = None,
        messages: list[Any],
        tools: list[Any] | None = None,
        **kwargs: Any,
    ) -> Any: ...


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries must be at least 0")
        if self.base_delay <= 0:
            raise ValueError("base_delay must be greater than 0")
        if self.max_delay <= 0:
            raise ValueError("max_delay must be greater than 0")
        if self.max_delay < self.base_delay:
            raise ValueError("max_delay must be greater than or equal to base_delay")


@dataclass(frozen=True)
class CompletionSettings:
    model: str | None = None
    fallback_models: tuple[str, ...] = ()
    retry: RetryPolicy = field(default_factory=RetryPolicy)

    def model_chain(self) -> tuple[str, ...]:
        """Deduped [model] + fallbacks, skipping empties."""
        chain: list[str] = []
        seen: set[str] = set()
        for candidate in (self.model, *self.fallback_models):
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            chain.append(candidate)
        return tuple(chain)


class CompletionClient:
    """Owns completion settings for one article run; call with request payload only."""

    def __init__(
        self,
        complete: CompletionFn,
        settings: CompletionSettings,
    ) -> None:
        self._complete = complete
        self._settings = settings

    @property
    def settings(self) -> CompletionSettings:
        return self._settings

    async def complete(
        self,
        *,
        messages: list[Any],
        tools: list[Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Retry + model fallback using owned settings; kwargs are request-only.

        For each model in ``settings.model_chain()``:
        1. Attempt the call.
        2. On a retryable error, wait with exponential backoff and retry up to
           ``settings.retry.max_retries`` additional times on the same model.
        3. If that model is exhausted, move to the next fallback model.
        4. Non-retryable errors are raised immediately.
        """
        models = self._settings.model_chain()
        if not models:
            # Preserve callers that inject fakes without configuring a model.
            return await self._complete(
                model=self._settings.model,
                messages=messages,
                tools=tools,
                **kwargs,
            )

        retry = self._settings.retry
        last_error: BaseException | None = None
        for model_index, candidate in enumerate(models):
            for attempt in range(retry.max_retries + 1):
                try:
                    return await self._complete(
                        model=candidate,
                        messages=messages,
                        tools=tools,
                        **kwargs,
                    )
                except Exception as exc:
                    if not is_retryable_error(exc):
                        raise

                    last_error = exc
                    is_last_attempt = attempt >= retry.max_retries
                    is_last_model = model_index >= len(models) - 1

                    if is_last_attempt and is_last_model:
                        break

                    if is_last_attempt:
                        logger.warning(
                            "Model %s exhausted after %d retries (%s); "
                            "falling back to %s",
                            candidate,
                            retry.max_retries,
                            exc,
                            models[model_index + 1],
                        )
                        break

                    delay = retry_delay_seconds(
                        attempt,
                        base_delay=retry.base_delay,
                        max_delay=retry.max_delay,
                        error=exc,
                    )
                    logger.warning(
                        "Retryable error on model %s (attempt %d/%d): %s; "
                        "retrying in %.2fs",
                        candidate,
                        attempt + 1,
                        retry.max_retries + 1,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)

        assert last_error is not None
        raise last_error


def make_completion_client(settings: CompletionSettings) -> CompletionClient:
    """Build a CompletionClient with the default LiteLLM transport."""
    return CompletionClient(make_litellm_completion(), settings)


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
    error: BaseException | None = None,
) -> float:
    """Exponential backoff with full jitter for retry attempt N (0-indexed).

    When the provider suggests a wait ("Please try again in 3.188s"), honor that
    floor so TPM rate limits are not immediately re-hit.
    """
    ceiling = min(max_delay, base_delay * (2**attempt))
    delay = random.uniform(0, ceiling)
    suggested = suggested_retry_delay_seconds(error) if error is not None else None
    if suggested is not None:
        delay = max(delay, min(max_delay, suggested + random.uniform(0.05, 0.35)))
    return delay


def suggested_retry_delay_seconds(exc: BaseException | None) -> float | None:
    """Parse provider-suggested retry delays from rate-limit errors."""
    if exc is None:
        return None

    header_delay = _retry_after_header_seconds(exc)
    if header_delay is not None:
        return header_delay

    match = _RETRY_AFTER_RE.search(str(exc))
    if match is None:
        return None
    value = float(match.group(1))
    unit = (match.group(2) or "s").lower()
    if unit == "ms":
        return value / 1000.0
    return value


def _retry_after_header_seconds(exc: BaseException) -> float | None:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        raw = headers.get("retry-after")  # type: ignore[call-arg]
    except Exception:
        return None
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def make_litellm_completion() -> CompletionFn:
    """Return the default LiteLLM async completion function."""
    import litellm

    async def complete(**kwargs: Any) -> Any:
        model = kwargs.get("model")
        if kwargs.get("tools") and _requires_none_reasoning_with_tools(model):
            kwargs.setdefault("reasoning_effort", "none")
        return await litellm.acompletion(**kwargs)

    return complete


def _requires_none_reasoning_with_tools(model: str | None) -> bool:
    """Some OpenAI reasoning models reject tools unless reasoning_effort is none."""
    if not model:
        return False

    lowered = model.lower()
    if "luna" in lowered or "gpt-5.6" in lowered:
        return True

    try:
        import litellm

        info = litellm.model_cost.get(model) or {}
        if not info:
            bare = model.split("/", 1)[-1]
            info = litellm.model_cost.get(bare) or {}
        return bool(
            info.get("supports_reasoning")
            and info.get("supports_none_reasoning_effort")
            and info.get("supports_function_calling")
        )
    except Exception:
        return False
