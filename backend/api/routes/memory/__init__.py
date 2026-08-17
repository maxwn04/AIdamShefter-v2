"""Competition-scoped canonical-memory route assembly."""

from fastapi import APIRouter

from backend.api.errors.memory import MemoryErrorResponse
from backend.api.routes.memory.context_notes import router as context_notes_router
from backend.api.routes.memory.events import router as events_router
from backend.api.routes.memory.facts import router as facts_router
from backend.api.routes.memory.revisions import router as revisions_router
from backend.api.routes.memory.search import router as search_router
from backend.api.routes.memory.storylines import router as storylines_router
from backend.api.routes.memory.triggers import router as triggers_router

router = APIRouter(
    prefix="/memory/competitions/{competition_id}",
    tags=["memory"],
    responses={
        400: {"model": MemoryErrorResponse},
        404: {"model": MemoryErrorResponse},
        409: {"model": MemoryErrorResponse},
        500: {"model": MemoryErrorResponse},
    },
)
router.include_router(revisions_router)
router.include_router(facts_router)
router.include_router(events_router)
router.include_router(storylines_router)
router.include_router(triggers_router)
router.include_router(context_notes_router)
router.include_router(search_router)

__all__ = ["router"]
