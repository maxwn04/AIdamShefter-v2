"""Route assembly for the AIdam API."""

from fastapi import APIRouter

from backend.api.routes.data import router as data_router
from backend.api.routes.generations import router as generations_router
from backend.api.routes.health import router as health_router
from backend.api.routes.memory import router as memory_router

api_router = APIRouter()
api_router.include_router(generations_router)
api_router.include_router(memory_router)
api_router.include_router(data_router)

__all__ = ["api_router", "health_router"]
