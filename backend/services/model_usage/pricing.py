"""Lazy access to LiteLLM's published model metadata and token prices."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from importlib.metadata import distribution
import json
from pathlib import Path
from threading import Lock
from typing import Any, cast

import requests

from backend.resources.reporting.ai_calls import TokenUsage


ModelInfo = Mapping[str, Any]
ModelMap = Mapping[str, ModelInfo]
ModelMapLoader = Callable[[], ModelMap]

LITELLM_MODEL_MAP_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)


class LiteLLMModelRegistry:
    """Cache LiteLLM metadata and quote standard text-token usage."""

    def __init__(
        self,
        *,
        remote_loader: ModelMapLoader | None = None,
        fallback_loader: ModelMapLoader | None = None,
    ) -> None:
        self._remote_loader = remote_loader or _load_remote_model_map
        self._fallback_loader = fallback_loader or _load_bundled_model_map
        self._model_map: ModelMap | None = None
        self._lock = Lock()

    def model_info(
        self,
        model: str,
        provider: str | None = None,
    ) -> ModelInfo | None:
        resolved = self._resolve(model, provider)
        return resolved[1] if resolved is not None else None

    def provider_for(self, model: str) -> str | None:
        info = self.model_info(model)
        if info is not None:
            provider = info.get("litellm_provider")
            if isinstance(provider, str) and provider.strip():
                return provider.strip()
        prefix, separator, _ = model.partition("/")
        return prefix if separator and prefix else None

    def quote(
        self,
        provider: str | None,
        model: str,
        usage: TokenUsage,
    ) -> Decimal | None:
        """Return a current USD estimate for normalized text-token usage."""

        resolved = self._resolve(model, provider)
        if resolved is None:
            return None
        _, info = resolved
        input_rate = _rate(info, "input_cost_per_token")
        output_rate = _rate(info, "output_cost_per_token")
        cached_rate = _first_rate(
            info,
            "cache_read_input_token_cost",
            "input_cost_per_token_cache_hit",
        )
        reasoning_rate = _rate(info, "output_cost_per_reasoning_token")

        if usage.input_tokens is None and usage.output_tokens is None:
            return None
        cost = Decimal(0)
        if usage.input_tokens is not None:
            if input_rate is None:
                return None
            cached = usage.cached_input_tokens or 0
            if cached > usage.input_tokens:
                return None
            regular_input = usage.input_tokens - cached
            cost += Decimal(regular_input) * input_rate
            cost += Decimal(cached) * (cached_rate or input_rate)
        if usage.output_tokens is not None:
            if output_rate is None:
                return None
            reasoning = usage.reasoning_tokens or 0
            if reasoning > usage.output_tokens:
                return None
            regular_output = usage.output_tokens - reasoning
            cost += Decimal(regular_output) * output_rate
            cost += Decimal(reasoning) * (reasoning_rate or output_rate)
        return cost

    def _resolve(
        self,
        model: str,
        provider: str | None,
    ) -> tuple[str, ModelInfo] | None:
        model_map = self._models()
        candidates: list[str] = []
        if provider and not model.startswith(f"{provider}/"):
            candidates.append(f"{provider}/{model}")
        candidates.append(model)
        if "/" in model:
            candidates.append(model.split("/", 1)[1])
        for candidate in candidates:
            info = model_map.get(candidate)
            if isinstance(info, Mapping):
                return candidate, cast(ModelInfo, info)
        return None

    def _models(self) -> ModelMap:
        if self._model_map is not None:
            return self._model_map
        with self._lock:
            if self._model_map is None:
                try:
                    loaded = self._remote_loader()
                except Exception:
                    loaded = self._fallback_loader()
                self._model_map = loaded
        return self._model_map


def _load_remote_model_map() -> ModelMap:
    response = requests.get(LITELLM_MODEL_MAP_URL, timeout=(3.0, 10.0))
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("LiteLLM model map must be a JSON object")
    return cast(ModelMap, payload)


def _load_bundled_model_map() -> ModelMap:
    package_file = distribution("litellm").locate_file(
        "litellm/model_prices_and_context_window_backup.json"
    )
    path = Path(package_file)
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("bundled LiteLLM model map must be a JSON object")
    return cast(ModelMap, payload)


def _rate(info: ModelInfo, name: str) -> Decimal | None:
    raw = info.get(name)
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return None
    try:
        rate = Decimal(str(raw))
    except Exception:
        return None
    return rate if rate >= 0 and rate.is_finite() else None


def _first_rate(info: ModelInfo, *names: str) -> Decimal | None:
    for name in names:
        rate = _rate(info, name)
        if rate is not None:
            return rate
    return None
