"""Persistent context store for cross-run agent memory.

Stores storylines, team context, and league-wide notes in a file-backed
SQLite database. This gives the research agent memory across runs while
keeping the existing fresh-load pattern for Sleeper API data.

Usage:
    store = ContextStore(".data/context.db", league_id="123", season="2024")
    context = store.get_full_context()
    store.upsert_storyline({...})
"""

from __future__ import annotations

from reporter_memory.schema import SCHEMA_VERSION
from reporter_memory.store.access import AccessMixin
from reporter_memory.store.base import StoreBase
from reporter_memory.store.events import EventsMixin
from reporter_memory.store.fts import FtsMixin
from reporter_memory.store.storylines import StorylinesMixin
from reporter_memory.store.triggers import TriggersMixin

__all__ = ["SCHEMA_VERSION", "ContextStore"]


class ContextStore(
    StorylinesMixin,
    EventsMixin,
    TriggersMixin,
    AccessMixin,
    FtsMixin,
    StoreBase,
):
    """File-backed SQLite store for persistent agent context.

    Each instance is scoped to a league_id + season pair. The underlying
    database file can hold data for multiple leagues/seasons.
    """

