"""Normalize and sanitize provider telemetry for durable model-call recording."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
import math
import re
from typing import Any, cast
from uuid import UUID

from pydantic import JsonValue

from backend.services.reporter.runner.recording import RecordedTokenUsage

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
    provider = error_provider(exc) or requested_provider
    if provider is not None:
        error["provider"] = provider
    return error


def json_object(
    value: Any,
    *,
    redact_sensitive: bool = True,
) -> dict[str, JsonValue]:
    """Convert an arbitrary provider value into a JSON object."""
    converted = _json_safe(value, redact_sensitive=redact_sensitive)
    if isinstance(converted, dict):
        return cast(dict[str, JsonValue], converted)
    return {"value": cast(JsonValue, converted)}


def response_finish_reason(response: Any) -> str | None:
    choices = _read_attr(response, "choices", []) or []
    try:
        first_choice = choices[0]
    except (IndexError, KeyError, TypeError):
        return None
    return _non_blank(_read_attr(first_choice, "finish_reason"))


def response_provider(response: Any) -> str | None:
    direct = _non_blank(_read_attr(response, "provider"))
    if direct is not None:
        return direct
    hidden = _read_attr(response, "_hidden_params", {}) or {}
    return _non_blank(_read_attr(hidden, "custom_llm_provider"))


def response_request_id(response: Any) -> str | None:
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


def response_model(response: Any) -> str | None:
    return _non_blank(_read_attr(response, "model"))


def response_id(response: Any) -> str | None:
    return _non_blank(_read_attr(response, "id"))


def error_provider(exc: BaseException) -> str | None:
    return _non_blank(
        _read_attr(exc, "provider") or _read_attr(exc, "llm_provider")
    )


def error_request_id(exc: BaseException) -> str | None:
    return _non_blank(_read_attr(exc, "request_id"))


def model_provider(model: str | None) -> str | None:
    if not model or "/" not in model:
        return None
    provider, _ = model.split("/", 1)
    return provider or None


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


def _first_scalar(value: Any, *names: str) -> JsonValue | None:
    for name in names:
        candidate = _read_attr(value, name)
        if candidate is None or isinstance(candidate, (dict, list, tuple, set)):
            continue
        sanitized = _json_safe(candidate)
        if isinstance(sanitized, (str, int, float, bool)):
            return sanitized
    return None


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
    return _ASSIGNED_SECRET_RE.sub(
        lambda match: f"{match.group(1)}={_REDACTED}",
        redacted,
    )


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


__all__ = [
    "error_provider",
    "error_request_id",
    "json_object",
    "model_provider",
    "normalize_token_usage",
    "response_finish_reason",
    "response_id",
    "response_model",
    "response_provider",
    "response_request_id",
    "sanitize_provider_error",
    "sanitize_provider_response",
]
