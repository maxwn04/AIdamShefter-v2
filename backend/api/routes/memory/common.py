"""Shared transport envelopes for canonical-memory routes."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from backend.services.memory import MemoryMutationResult


class MemoryApiModel(BaseModel):
    """Strict HTTP model kept separate from persistence contracts."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class MemoryMutationResponse(MemoryApiModel):
    result: MemoryMutationResult
