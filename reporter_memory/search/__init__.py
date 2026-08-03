"""Agent-facing memory search, candidate expansion, and verification planning.

Uses ContextStore for SQL/CRUD; this package owns ranking, lead shaping, and
verification hints for reporter tools.
"""

from reporter_memory.search.candidates import get_memory_candidate, normalize_owner_type
from reporter_memory.search.pipeline import search_story_memory
from reporter_memory.search.verification import (
    plan_memory_verification,
    normalize_verification_fact_links,
    validate_verified_fact_links,
)

__all__ = [
    "get_memory_candidate",
    "normalize_owner_type",
    "normalize_verification_fact_links",
    "plan_memory_verification",
    "search_story_memory",
    "validate_verified_fact_links",
]
