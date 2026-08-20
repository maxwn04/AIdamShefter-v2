"""Normalized Sleeper scope resource."""

from backend.resources.sleeper_data.normalized_scopes.manager import (
    NormalizedScopeManager,
)
from backend.resources.sleeper_data.normalized_scopes.objects import ApplyResult

__all__ = ["ApplyResult", "NormalizedScopeManager"]
