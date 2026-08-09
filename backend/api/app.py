"""FastAPI application factory and local server entry point."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
import uvicorn

from backend.api.routes import api_router, health_router
from backend.composition import ApiRuntimeDependencies, build_api_runtime

RuntimeFactory = Callable[[], ApiRuntimeDependencies]


def create_app(
    *,
    runtime_factory: RuntimeFactory = build_api_runtime,
) -> FastAPI:
    """Create an API process with explicitly owned runtime dependencies."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime = runtime_factory()
        app.state.runtime = runtime
        try:
            yield
        finally:
            runtime.close()

    application = FastAPI(
        title="AIdam API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(health_router)
    application.include_router(api_router, prefix="/api/v1")
    return application


app = create_app()


def main() -> None:
    """Run the local API server with Uvicorn."""

    host = os.getenv("AIDAM_API_HOST", "127.0.0.1")
    port = int(os.getenv("AIDAM_API_PORT", "8000"))
    uvicorn.run("backend.api.app:app", host=host, port=port)
