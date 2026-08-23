"""FastAPI application factory and local server entry point."""

import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from backend.api.errors import (
    REPORTING_APPLICATION_ERRORS,
    core_resource_error_handler,
    datalayer_error_handler,
    memory_application_error_handler,
    reporting_application_error_handler,
)
from backend.api.routes import api_router, health_router
from backend.composition import ApiRuntimeDependencies, build_api_runtime
from backend.resources.core import CoreResourceError
from backend.resources.memory.common import MemoryApplicationError
from backend.services.datalayer import DatalayerError

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
    application.add_exception_handler(
        MemoryApplicationError,
        memory_application_error_handler,
    )
    application.add_exception_handler(
        CoreResourceError,
        core_resource_error_handler,
    )
    application.add_exception_handler(
        DatalayerError,
        datalayer_error_handler,
    )
    for error_type in REPORTING_APPLICATION_ERRORS:
        application.add_exception_handler(
            error_type,
            reporting_application_error_handler,
        )
    return application


app = create_app()


def main() -> None:
    """Run the local API server with Uvicorn."""

    host = os.getenv("AIDAM_API_HOST", "127.0.0.1")
    port = int(os.getenv("AIDAM_API_PORT", "8000"))
    uvicorn.run("backend.api.app:app", host=host, port=port)
