from collections.abc import Callable
from typing import final

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.exc import SQLAlchemyError

from backend.api.app import create_app
from backend.composition import ApiRuntimeDependencies


@final
class StubRuntime:
    def __init__(self, readiness_error: Exception | None = None) -> None:
        self.readiness_error = readiness_error
        self.readiness_checks = 0
        self.closed = False

    def assert_ready(self) -> None:
        self.readiness_checks += 1
        if self.readiness_error is not None:
            raise self.readiness_error

    def close(self) -> None:
        self.closed = True


def runtime_factory(runtime: StubRuntime) -> Callable[[], ApiRuntimeDependencies]:
    return lambda: runtime


@pytest.mark.asyncio
async def test_liveness_does_not_query_database() -> None:
    runtime = StubRuntime()
    app = create_app(runtime_factory=runtime_factory(runtime))

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert runtime.readiness_checks == 0
    assert runtime.closed is True


@pytest.mark.asyncio
async def test_readiness_checks_database_runtime() -> None:
    runtime = StubRuntime()
    app = create_app(runtime_factory=runtime_factory(runtime))

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert runtime.readiness_checks == 1


@pytest.mark.parametrize(
    "error",
    [RuntimeError("wrong role"), SQLAlchemyError("database down")],
)
@pytest.mark.asyncio
async def test_readiness_returns_safe_unavailable_response(
    error: Exception,
) -> None:
    runtime = StubRuntime(error)
    app = create_app(runtime_factory=runtime_factory(runtime))

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "service is not ready"}
    assert str(error) not in response.text


def test_api_metadata() -> None:
    runtime = StubRuntime()
    app = create_app(runtime_factory=runtime_factory(runtime))

    assert app.title == "AIdam API"
    assert app.version == "0.1.0"
