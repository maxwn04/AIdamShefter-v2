"""Transport-safe model catalog and generation usage projections."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field

from backend.resources._contracts import ContractModel


NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]


class ModelCatalogItem(ContractModel):
    provider: str | None
    model: str
    display_name: str
    is_default: bool
    supports_reasoning: bool


class ModelCatalog(ContractModel):
    models: tuple[ModelCatalogItem, ...]


class TokenTotals(ContractModel):
    input_tokens: NonNegativeInt = 0
    cached_input_tokens: NonNegativeInt = 0
    output_tokens: NonNegativeInt = 0
    reasoning_tokens: NonNegativeInt = 0
    total_tokens: NonNegativeInt = 0


class ModelUsageBreakdown(ContractModel):
    provider: str | None
    model: str | None
    attempt_count: NonNegativeInt
    latency_ms: NonNegativeInt
    tokens: TokenTotals
    estimated_cost: str | None
    currency: str
    complete: bool


class GenerationUsage(ContractModel):
    generation_id: UUID
    attempt_count: NonNegativeInt
    latency_ms: NonNegativeInt
    tokens: TokenTotals
    breakdowns: tuple[ModelUsageBreakdown, ...]
    estimated_cost: str | None
    currency: str
    complete: bool
    missing_usage_call_ids: tuple[UUID, ...]
    unpriced_call_ids: tuple[UUID, ...]
    quoted_at: AwareDatetime
