"""Sleeper-data HTTP routes.

Handlers will be added with the ingestion and snapshot service boundary.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/data", tags=["data"])
