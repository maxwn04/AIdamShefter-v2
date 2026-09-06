"""Embedding boundary: identifiable models and strictly validated vectors."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import math
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class EmbeddingSpec:
    provider: str = "openai"
    model: str = "text-embedding-3-large"
    dimensions: int = 3072
    text_format_version: int = 1

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.model.strip():
            raise ValueError("Embedding provider and model must be nonblank")
        if self.dimensions <= 0 or self.text_format_version != 1:
            raise ValueError("Positive dimensions and supported text format version 1 are required")


class EmbeddingProvider(Protocol):
    @property
    def spec(self) -> EmbeddingSpec: ...

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


def validated_vectors(
    vectors: Sequence[Sequence[float]], *, count: int, dimensions: int,
) -> tuple[tuple[float, ...], ...]:
    if len(vectors) != count:
        raise ValueError("Embedding response count does not match input")
    result: list[tuple[float, ...]] = []
    for raw in vectors:
        if len(raw) != dimensions:
            raise ValueError("Embedding response dimensions do not match model identity")
        if any(isinstance(value, bool) for value in raw):
            raise ValueError("Embedding values must be numeric")
        vector = tuple(float(value) for value in raw)
        if not all(math.isfinite(value) for value in vector):
            raise ValueError("Embedding values must be finite")
        norm = math.hypot(*vector)
        if not math.isfinite(norm) or norm == 0:
            raise ValueError("Embedding vectors require a finite nonzero norm")
        result.append(vector)
    return tuple(result)


class OpenAIEmbeddingProvider:
    """Opt-in synchronous adapter using the existing LiteLLM dependency.

    Construction performs no IO. Calls have no automatic retry or document
    indexing side effects. The application decides when paid calls are allowed.
    """

    def __init__(
        self, spec: EmbeddingSpec | None = None, *, timeout_seconds: float = 30,
        embedding_call: Callable[..., Any] | None = None,
    ) -> None:
        self.spec = spec or EmbeddingSpec()
        if self.spec.provider != "openai":
            raise ValueError("OpenAIEmbeddingProvider requires provider=openai")
        self._timeout = timeout_seconds
        self._call = embedding_call

    def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        call = self._call
        if call is None:
            from litellm import embedding

            call = embedding
        response = call(
            model=self.spec.model, input=list(texts), dimensions=self.spec.dimensions,
            timeout=self._timeout, num_retries=0,
        )
        data = response["data"]
        indexed = sorted(data, key=lambda value: value["index"])
        if [value["index"] for value in indexed] != list(range(len(texts))):
            raise ValueError("Embedding response indices do not match input")
        return validated_vectors(
            [value["embedding"] for value in indexed],
            count=len(texts), dimensions=self.spec.dimensions,
        )
