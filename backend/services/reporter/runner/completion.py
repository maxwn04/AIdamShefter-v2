"""Resilient LiteLLM completion with retry and model fallback."""

from __future__ import annotations

import asyncio
import logging
import random
import re
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from backend.services.reporter.runner.provider_telemetry import (
    error_provider,
    error_request_id,
    json_object,
    model_provider,
    normalize_token_usage,
    response_finish_reason,
    response_id,
    response_model,
    response_provider,
    response_request_id,
    sanitize_provider_error,
    sanitize_provider_response,
)
from backend.services.reporter.runner.recording import (
    CompletionRecorder,
    ModelAttemptFinish,
    ModelAttemptStart,
)

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


class CompletionRecordingError(RuntimeError):
    """Durable recording failed, so the provider operation cannot continue."""


class ProviderConfigurationError(RuntimeError):
    """A trusted provider configuration failure that must not be retried."""

    public_summary = (
        "Reporter execution cannot start because OPENAI_API_KEY is not configured"
    )

    def __init__(self) -> None:
        super().__init__(self.public_summary)


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
        recorder: CompletionRecorder | None = None,
    ) -> None:
        self._complete = complete
        self._settings = settings
        self._recorder = recorder

    @property
    def settings(self) -> CompletionSettings:
        return self._settings

    @property
    def recorder(self) -> CompletionRecorder | None:
        return self._recorder

    async def complete(
        self,
        *,
        turn_number: int | None = None,
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
        if self._recorder is not None and (
            isinstance(turn_number, bool)
            or not isinstance(turn_number, int)
            or turn_number < 1
        ):
            raise ValueError("recorded completions require a positive turn_number")

        models = self._settings.model_chain()
        if not models:
            if self._recorder is not None:
                raise ValueError("recorded completions require a configured model")
            # Preserve callers that inject fakes without configuring a model.
            return await self._complete_once(
                candidate=self._settings.model,
                turn_number=turn_number,
                messages=messages,
                tools=tools,
                request_parameters=kwargs,
            )

        retry = self._settings.retry
        last_error: BaseException | None = None
        for model_index, candidate in enumerate(models):
            for attempt in range(retry.max_retries + 1):
                try:
                    return await self._complete_once(
                        candidate=candidate,
                        turn_number=turn_number,
                        messages=messages,
                        tools=tools,
                        request_parameters=kwargs,
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

    async def _complete_once(
        self,
        *,
        candidate: str | None,
        turn_number: int | None,
        messages: list[Any],
        tools: list[Any] | None,
        request_parameters: dict[str, Any],
    ) -> Any:
        parameters = dict(request_parameters)
        if tools and _requires_none_reasoning_with_tools(candidate):
            parameters.setdefault("reasoning_effort", "none")

        requested_provider = model_provider(candidate)
        attempt_id: UUID | None = None
        if self._recorder is not None:
            assert candidate is not None
            assert turn_number is not None
            try:
                attempt_id = self._recorder.begin_model_attempt(
                    ModelAttemptStart(
                        turn_number=turn_number,
                        requested_provider=requested_provider,
                        requested_model=candidate,
                        input_messages=tuple(
                            json_object(message, redact_sensitive=False)
                            for message in messages
                        ),
                        tool_definitions=tuple(
                            json_object(tool, redact_sensitive=False)
                            for tool in tools or ()
                        ),
                        request_parameters=json_object(parameters),
                    )
                )
            except Exception as exc:
                raise CompletionRecordingError(
                    "model attempt recording failed before provider invocation"
                ) from exc

        try:
            response = await self._complete(
                model=candidate,
                messages=messages,
                tools=tools,
                **parameters,
            )
        except asyncio.CancelledError as exc:
            self._finish_recorded_attempt(
                attempt_id,
                ModelAttemptFinish(
                    status="unknown_outcome",
                    actual_provider=requested_provider,
                    actual_model=candidate,
                    error=sanitize_provider_error(exc, requested_provider),
                ),
            )
            raise
        except Exception as exc:
            provider_error = _normalize_provider_error(exc)
            status = (
                "retryable_error"
                if is_retryable_error(provider_error)
                else "fatal_error"
            )
            self._finish_recorded_attempt(
                attempt_id,
                ModelAttemptFinish(
                    status=status,
                    actual_provider=error_provider(exc) or requested_provider,
                    actual_model=candidate,
                    error=sanitize_provider_error(provider_error, requested_provider),
                    provider_request_id=error_request_id(exc),
                ),
            )
            if provider_error is not exc:
                raise provider_error from exc
            raise

        self._finish_recorded_attempt(
            attempt_id,
            ModelAttemptFinish(
                status="succeeded",
                actual_provider=response_provider(response) or requested_provider,
                actual_model=response_model(response) or candidate,
                provider_response=sanitize_provider_response(response),
                finish_reason=response_finish_reason(response),
                provider_request_id=response_request_id(response),
                provider_response_id=response_id(response),
                usage=normalize_token_usage(response),
            ),
        )
        return response

    def _finish_recorded_attempt(
        self,
        attempt_id: UUID | None,
        result: ModelAttemptFinish,
    ) -> None:
        if self._recorder is not None:
            assert attempt_id is not None
            try:
                self._recorder.finish_model_attempt(attempt_id, result)
            except Exception as exc:
                raise CompletionRecordingError(
                    "model attempt recording failed after provider invocation"
                ) from exc


def make_completion_client(
    settings: CompletionSettings,
    recorder: CompletionRecorder | None = None,
) -> CompletionClient:
    """Build a CompletionClient with the default LiteLLM transport."""
    return CompletionClient(make_litellm_completion(), settings, recorder)


def is_retryable_error(exc: BaseException) -> bool:
    """Return True when the error looks transient / rate-limited."""
    if isinstance(exc, ProviderConfigurationError):
        return False

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


def _normalize_provider_error(exc: Exception) -> Exception:
    message = str(exc).casefold()
    if (
        "openai_api_key" in message
        and "missing credentials" in message
        and "please pass" in message
        and "api_key" in message
    ):
        return ProviderConfigurationError()
    return exc


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
