"""Generation HTTP routes.

Handlers will be added with the generation manager and service boundary.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/generations", tags=["generations"])
