"""Access to process-scoped services and infrastructure."""

from typing import cast

from fastapi import Request

from backend.composition import ApiRuntimeDependencies


def get_api_runtime(request: Request) -> ApiRuntimeDependencies:
    """Return dependencies built by the application lifespan."""

    return cast(ApiRuntimeDependencies, request.app.state.runtime)
