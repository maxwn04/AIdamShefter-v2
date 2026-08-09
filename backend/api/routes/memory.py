"""Reporter-memory HTTP routes.

Handlers will be added with the canonical-memory manager and service boundary.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/memory", tags=["memory"])
