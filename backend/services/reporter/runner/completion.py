"""Resilient LiteLLM completion with retry and model fallback."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
import logging
import math
import random
import re
from dataclasses import dataclass, field
from typing import Any, Protocol, cast
from uuid import UUID

from pydantic import JsonValue

from backend.services.reporter.runner.recording import (
    CompletionRecorder,
    ModelAttemptFinish,
    ModelAttemptStart,
    RecordedTokenUsage,
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

_REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "proxyauthorization",
        "apikey",
        "xapikey",
        "accesstoken",
        "refreshtoken",
        "clientsecret",
        "cookie",
        "setcookie",
    }
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]+=*")
_OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_ASSIGNED_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|client[_-]?secret)(\s*[=:]\s*)\S+"
)
_MAX_ERROR_MESSAGE_LENGTH = 2000


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

        requested_provider = _model_provider(candidate)
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
                            _json_object(message, redact_sensitive=False)
                            for message in messages
                        ),
                        tool_definitions=tuple(
                            _json_object(tool, redact_sensitive=False)
                            for tool in tools or ()
                        ),
                        request_parameters=_json_object(parameters),
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
            status = "retryable_error" if is_retryable_error(exc) else "fatal_error"
            self._finish_recorded_attempt(
                attempt_id,
                ModelAttemptFinish(
                    status=status,
                    actual_provider=_error_provider(exc) or requested_provider,
                    actual_model=candidate,
                    error=sanitize_provider_error(exc, requested_provider),
                    provider_request_id=_error_request_id(exc),
                ),
            )
            raise

        self._finish_recorded_attempt(
            attempt_id,
            ModelAttemptFinish(
                status="succeeded",
                actual_provider=_response_provider(response) or requested_provider,
                actual_model=_non_blank(_read_attr(response, "model")) or candidate,
                provider_response=sanitize_provider_response(response),
                finish_reason=_response_finish_reason(response),
                provider_request_id=_response_request_id(response),
                provider_response_id=_non_blank(_read_attr(response, "id")),
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


def normalize_token_usage(response: Any) -> RecordedTokenUsage:
    """Map only explicitly reported provider token categories."""
    usage = _read_attr(response, "usage")
    if usage is None:
        return RecordedTokenUsage()

    raw = _json_safe(usage)
    raw_usage = raw if isinstance(raw, dict) else {"value": raw}
    return RecordedTokenUsage(
        input_tokens=_first_token(usage, "prompt_tokens", "input_tokens"),
        cached_input_tokens=_first_present(
            _nested_token(usage, "prompt_tokens_details", "cached_tokens"),
            _nested_token(usage, "input_tokens_details", "cached_tokens"),
            _first_token(usage, "cache_read_input_tokens", "cached_tokens"),
        ),
        output_tokens=_first_token(usage, "completion_tokens", "output_tokens"),
        reasoning_tokens=_first_present(
            _nested_token(usage, "completion_tokens_details", "reasoning_tokens"),
            _nested_token(usage, "output_tokens_details", "reasoning_tokens"),
            _first_token(usage, "reasoning_tokens"),
        ),
        total_tokens=_first_token(usage, "total_tokens"),
        raw_provider_usage=cast(dict[str, JsonValue], raw_usage),
    )


def sanitize_provider_response(response: Any) -> dict[str, JsonValue]:
    """Return complete JSON-safe provider output with secret fields redacted."""
    value = _json_safe(response)
    if isinstance(value, dict):
        return cast(dict[str, JsonValue], value)
    return {"value": cast(JsonValue, value)}


def sanitize_provider_error(
    exc: BaseException,
    requested_provider: str | None = None,
) -> dict[str, JsonValue]:
    """Build a bounded error envelope without transport or credential objects."""
    message = _redact_string(str(exc))[:_MAX_ERROR_MESSAGE_LENGTH]
    error: dict[str, JsonValue] = {
        "type": type(exc).__name__,
        "message": message,
    }
    for output_name, attribute_names in (
        ("status_code", ("status_code", "status")),
        ("code", ("code",)),
        ("request_id", ("request_id",)),
    ):
        value = _first_scalar(exc, *attribute_names)
        if value is not None:
            error[output_name] = value
    provider = _error_provider(exc) or requested_provider
    if provider is not None:
        error["provider"] = provider
    return error


def _first_token(value: Any, *names: str) -> int | None:
    for name in names:
        token_count = _read_attr(value, name)
        if (
            isinstance(token_count, int)
            and not isinstance(token_count, bool)
            and token_count >= 0
        ):
            return token_count
    return None


def _nested_token(value: Any, parent: str, child: str) -> int | None:
    nested = _read_attr(value, parent)
    return _first_token(nested, child) if nested is not None else None


def _first_present(*values: int | None) -> int | None:
    return next((value for value in values if value is not None), None)


def _response_finish_reason(response: Any) -> str | None:
    choices = _read_attr(response, "choices", []) or []
    try:
        first_choice = choices[0]
    except (IndexError, KeyError, TypeError):
        return None
    return _non_blank(_read_attr(first_choice, "finish_reason"))


def _response_provider(response: Any) -> str | None:
    direct = _non_blank(_read_attr(response, "provider"))
    if direct is not None:
        return direct
    hidden = _read_attr(response, "_hidden_params", {}) or {}
    return _non_blank(_read_attr(hidden, "custom_llm_provider"))


def _response_request_id(response: Any) -> str | None:
    direct = _non_blank(_read_attr(response, "request_id"))
    if direct is not None:
        return direct
    hidden = _read_attr(response, "_hidden_params", {}) or {}
    for container_name in ("additional_headers", "response_headers"):
        headers = _read_attr(hidden, container_name, {}) or {}
        for header_name in ("x-request-id", "request-id"):
            value = _case_insensitive_mapping_value(headers, header_name)
            if value is not None:
                return _non_blank(value)
    return None


def _error_provider(exc: BaseException) -> str | None:
    return _non_blank(
        _read_attr(exc, "provider") or _read_attr(exc, "llm_provider")
    )


def _error_request_id(exc: BaseException) -> str | None:
    return _non_blank(_read_attr(exc, "request_id"))


def _model_provider(model: str | None) -> str | None:
    if not model or "/" not in model:
        return None
    provider, _ = model.split("/", 1)
    return provider or None


def _first_scalar(value: Any, *names: str) -> JsonValue | None:
    for name in names:
        candidate = _read_attr(value, name)
        if candidate is None or isinstance(candidate, (dict, list, tuple, set)):
            continue
        sanitized = _json_safe(candidate)
        if isinstance(sanitized, (str, int, float, bool)):
            return sanitized
    return None


def _json_object(
    value: Any,
    *,
    redact_sensitive: bool = True,
) -> dict[str, JsonValue]:
    converted = _json_safe(value, redact_sensitive=redact_sensitive)
    if isinstance(converted, dict):
        return cast(dict[str, JsonValue], converted)
    return {"value": cast(JsonValue, converted)}


def _json_safe(
    value: Any,
    *,
    redact_sensitive: bool = True,
    depth: int = 0,
) -> JsonValue:
    if depth >= 20:
        return "<maximum depth>"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return _redact_string(value) if redact_sensitive else value
    if isinstance(value, Enum):
        return _json_safe(
            value.value,
            redact_sensitive=redact_sensitive,
            depth=depth + 1,
        )
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"

    model_dump = _read_attr(value, "model_dump")
    if callable(model_dump):
        try:
            dumped = model_dump(mode="json")
        except Exception:
            dumped = None
        if dumped is not None and dumped is not value:
            return _json_safe(
                dumped,
                redact_sensitive=redact_sensitive,
                depth=depth + 1,
            )
    if isinstance(value, Mapping):
        converted: dict[str, JsonValue] = {}
        for key, nested in value.items():
            key_text = str(key)
            if redact_sensitive and _is_sensitive_key(key_text):
                converted[key_text] = _REDACTED
            else:
                converted[key_text] = _json_safe(
                    nested,
                    redact_sensitive=redact_sensitive,
                    depth=depth + 1,
                )
        return converted
    if isinstance(value, (list, tuple)):
        return [
            _json_safe(
                nested,
                redact_sensitive=redact_sensitive,
                depth=depth + 1,
            )
            for nested in value
        ]
    if isinstance(value, set):
        return [
            _json_safe(
                nested,
                redact_sensitive=redact_sensitive,
                depth=depth + 1,
            )
            for nested in sorted(value, key=str)
        ]

    public_attributes = _read_attr(value, "__dict__")
    if isinstance(public_attributes, dict):
        return _json_safe(
            {
                key: nested
                for key, nested in public_attributes.items()
                if not key.startswith("_")
            },
            redact_sensitive=redact_sensitive,
            depth=depth + 1,
        )
    try:
        text = str(value)
    except Exception:
        text = f"<{type(value).__name__}>"
    return _redact_string(text) if redact_sensitive else text


def _is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    return normalized in _SENSITIVE_KEYS


def _redact_string(value: str) -> str:
    redacted = _BEARER_RE.sub(_REDACTED, value)
    redacted = _OPENAI_KEY_RE.sub(_REDACTED, redacted)
    return _ASSIGNED_SECRET_RE.sub(lambda match: f"{match.group(1)}={_REDACTED}", redacted)


def _case_insensitive_mapping_value(value: Any, key: str) -> Any | None:
    if not isinstance(value, Mapping):
        return None
    target = key.casefold()
    return next(
        (nested for name, nested in value.items() if str(name).casefold() == target),
        None,
    )


def _non_blank(value: Any) -> str | None:
    if value is None:
        return None
    try:
        text = str(value).strip()
    except Exception:
        return None
    return text or None


def _read_attr(value: Any, name: str, default: Any = None) -> Any:
    try:
        if isinstance(value, Mapping):
            return value.get(name, default)
        return getattr(value, name, default)
    except Exception:
        return default
