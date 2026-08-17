from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, final
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.api.app import create_app
from backend.api.dependencies import get_memory_api_dependencies
from backend.composition import ApiRuntimeDependencies
from backend.resources.memory.common import (
    MemoryItemIdentity,
    MemoryKind,
    MemoryVersionMetadata,
    SearchProjectionHydrationError,
    StaleCanonicalRevisionError,
    TargetNotFoundError,
)
from backend.resources.memory.facts import Fact, FactContent
from backend.resources.memory.revisions import CanonicalRevision
from backend.services.memory import MemoryMutationResult, MemoryRetrievalResult


@final
class StubRuntime:
    def assert_ready(self) -> None:
        pass

    def close(self) -> None:
        pass


def runtime_factory() -> Callable[[], ApiRuntimeDependencies]:
    return StubRuntime


class StubResourceManager:
    def __init__(self, memory: Fact | None = None) -> None:
        self.memory = memory
        self.exact_ids: list[UUID] = []
        self.history_ids: list[UUID] = []

    def exact(self, version_id: UUID) -> Fact:
        self.exact_ids.append(version_id)
        if self.memory is None:
            raise TargetNotFoundError(version_id, (MemoryKind.FACT,))
        return self.memory

    def history(self, item_id: UUID) -> tuple[Fact, ...]:
        self.history_ids.append(item_id)
        if self.memory is None:
            raise TargetNotFoundError(item_id, (MemoryKind.FACT,))
        return (self.memory,)


class StubRevisionManager:
    def __init__(self, revision: CanonicalRevision) -> None:
        self.revision = revision

    def current(self) -> CanonicalRevision:
        return self.revision

    def pin(self, _revision_id: UUID) -> CanonicalRevision:
        return self.revision

    def history(self) -> tuple[CanonicalRevision, ...]:
        return (self.revision,)


class StubMutationService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.error = error

    def _call(self, name: str, *args: Any, **kwargs: Any) -> MemoryMutationResult:
        self.calls.append((name, args, kwargs))
        if self.error is not None:
            raise self.error
        return MemoryMutationResult(revision=None, changes=())

    def create_fact(self, *args: Any, **kwargs: Any) -> MemoryMutationResult:
        return self._call("create_fact", *args, **kwargs)

    def replace_fact(self, *args: Any, **kwargs: Any) -> MemoryMutationResult:
        return self._call("replace_fact", *args, **kwargs)

    def create_event(self, *args: Any, **kwargs: Any) -> MemoryMutationResult:
        return self._call("create_event", *args, **kwargs)

    def replace_event(self, *args: Any, **kwargs: Any) -> MemoryMutationResult:
        return self._call("replace_event", *args, **kwargs)

    def create_storyline(self, *args: Any, **kwargs: Any) -> MemoryMutationResult:
        return self._call("create_storyline", *args, **kwargs)

    def replace_storyline(self, *args: Any, **kwargs: Any) -> MemoryMutationResult:
        return self._call("replace_storyline", *args, **kwargs)

    def create_trigger(self, *args: Any, **kwargs: Any) -> MemoryMutationResult:
        return self._call("create_trigger", *args, **kwargs)

    def replace_trigger(self, *args: Any, **kwargs: Any) -> MemoryMutationResult:
        return self._call("replace_trigger", *args, **kwargs)

    def create_context_note(self, *args: Any, **kwargs: Any) -> MemoryMutationResult:
        return self._call("create_context_note", *args, **kwargs)

    def replace_context_note(self, *args: Any, **kwargs: Any) -> MemoryMutationResult:
        return self._call("replace_context_note", *args, **kwargs)


class StubRetrievalService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[tuple[UUID, UUID]] = []
        self.error = error

    def search(
        self,
        *,
        competition_id: UUID,
        revision_id: UUID,
        request: object,
    ) -> MemoryRetrievalResult:
        del request
        self.calls.append((competition_id, revision_id))
        if self.error is not None:
            raise self.error
        return MemoryRetrievalResult(
            competition_id=competition_id,
            revision_id=revision_id,
            matches=(),
        )


class StubMemoryDependencies:
    def __init__(
        self,
        *,
        competition_id: UUID,
        fact: Fact | None = None,
        mutation_error: Exception | None = None,
        retrieval_error: Exception | None = None,
    ) -> None:
        self.revisions = StubRevisionManager(_revision(competition_id))
        self.facts = StubResourceManager(fact)
        self.events = StubResourceManager()
        self.storylines = StubResourceManager()
        self.triggers = StubResourceManager()
        self.context_notes = StubResourceManager()
        self.mutations = StubMutationService(error=mutation_error)
        self.retrieval = StubRetrievalService(error=retrieval_error)


def _revision(competition_id: UUID) -> CanonicalRevision:
    return CanonicalRevision(
        revision_id=uuid4(),
        competition_id=competition_id,
        sequence_number=0,
        state_content_hash="seed-root",
        created_at=datetime(2026, 8, 17, tzinfo=UTC),
    )


def _fact(competition_id: UUID) -> Fact:
    generation_id = uuid4()
    content = FactContent.model_validate(
        {
            "claim": "The Owls won the opener.",
            "category": "result",
            "numbers": {"margin": 3},
            "confidence": "inferred",
            "status": "active",
            "subjects": [],
            "originating_event_version_ids": [],
        }
    )
    return Fact(
        item=MemoryItemIdentity(
            item_id=uuid4(),
            competition_id=competition_id,
            kind=MemoryKind.FACT,
            created_at=datetime(2026, 8, 17, tzinfo=UTC),
        ),
        version=MemoryVersionMetadata(
            version_id=uuid4(),
            revision_number=1,
            content_schema_version=1,
            introduced_revision_id=uuid4(),
            creating_generation_id=generation_id,
            recorded_at=datetime(2026, 8, 17, tzinfo=UTC),
        ),
        content=content,
    )


async def _request(
    dependencies: StubMemoryDependencies,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
) -> Any:
    app = create_app(runtime_factory=runtime_factory())
    app.dependency_overrides[get_memory_api_dependencies] = lambda: dependencies
    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, json=json)


@pytest.mark.asyncio
async def test_revision_and_fact_reads_return_transport_wrappers() -> None:
    competition_id = uuid4()
    fact = _fact(competition_id)
    dependencies = StubMemoryDependencies(competition_id=competition_id, fact=fact)
    base = f"/api/v1/memory/competitions/{competition_id}"

    current = await _request(dependencies, "GET", f"{base}/revisions/current")
    exact = await _request(
        dependencies,
        "GET",
        f"{base}/facts/versions/{fact.version.version_id}",
    )
    history = await _request(
        dependencies,
        "GET",
        f"{base}/facts/{fact.item.item_id}/history",
    )

    assert current.status_code == 200
    assert current.json()["revision"]["competition_id"] == str(competition_id)
    assert exact.status_code == 200
    assert exact.json()["memory"]["content"]["claim"] == "The Owls won the opener."
    assert history.status_code == 200
    assert len(history.json()["items"]) == 1


@pytest.mark.asyncio
async def test_search_requires_an_explicit_revision_and_returns_hydrated_result() -> None:
    competition_id = uuid4()
    revision_id = uuid4()
    dependencies = StubMemoryDependencies(competition_id=competition_id)
    response = await _request(
        dependencies,
        "POST",
        f"/api/v1/memory/competitions/{competition_id}/search",
        json={
            "revision_id": str(revision_id),
            "query": {"text": "rivalry"},
            "expand_exact_references": True,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "result": {
            "competition_id": str(competition_id),
            "revision_id": str(revision_id),
            "matches": [],
        }
    }
    assert dependencies.retrieval.calls == [(competition_id, revision_id)]


def _origin() -> dict[str, str]:
    return {
        "generation_id": str(uuid4()),
        "expected_revision_id": str(uuid4()),
    }


def _write_cases() -> tuple[tuple[str, dict[str, Any], str], ...]:
    franchise_a = uuid4()
    franchise_b = uuid4()
    season_id = uuid4()
    return (
        (
            "facts",
            {
                "origin": _origin(),
                "content": {
                    "claim": "The Owls won.",
                    "category": "result",
                    "numbers": {},
                    "confidence": "inferred",
                    "status": "active",
                    "subjects": [],
                    "originating_event_version_ids": [],
                },
            },
            "fact",
        ),
        (
            "events",
            {
                "origin": _origin(),
                "content": {
                    "event_type": "matchup",
                    "headline": "The Owls won.",
                    "summary": "A close opener.",
                    "salience": 3,
                    "confidence": "inferred",
                    "status": "active",
                    "details": {
                        "kind": "matchup",
                        "winner_franchise_id": str(franchise_a),
                        "loser_franchise_id": str(franchise_b),
                        "sleeper_matchup_id": "week-1",
                    },
                },
            },
            "event",
        ),
        (
            "storylines",
            {
                "origin": _origin(),
                "content": {
                    "headline": "A rivalry starts.",
                    "summary": "The opener created tension.",
                    "status": "active",
                    "salience": 3,
                    "tags": ["rivalry"],
                    "subjects": [],
                    "evidence": [],
                    "related_storylines": [],
                },
            },
            "storyline",
        ),
        (
            "triggers",
            {
                "origin": _origin(),
                "content": {
                    "trigger_type": "rematch",
                    "status": "open",
                    "fire_policy": "one_shot",
                    "target_competition_season_id": str(season_id),
                    "target_week": 8,
                    "condition": {
                        "kind": "rematch",
                        "franchise_ids": [str(franchise_a), str(franchise_b)],
                    },
                },
            },
            "trigger",
        ),
        (
            "context-notes",
            {
                "origin": _origin(),
                "identity": {
                    "scope": "competition",
                    "note_key": "league-tone",
                },
                "content": {
                    "narrative": "The league rewards aggressive trades.",
                    "status": "active",
                    "tags": ["culture"],
                },
            },
            "context_note",
        ),
    )


@pytest.mark.parametrize(("resource", "payload", "method_suffix"), _write_cases())
@pytest.mark.asyncio
async def test_create_and_replace_routes_delegate_complete_typed_writes(
    resource: str,
    payload: dict[str, Any],
    method_suffix: str,
) -> None:
    competition_id = uuid4()
    dependencies = StubMemoryDependencies(competition_id=competition_id)
    base = f"/api/v1/memory/competitions/{competition_id}/{resource}"

    created = await _request(dependencies, "POST", base, json=payload)
    replacement = dict(payload)
    replacement.pop("identity", None)
    replacement["expected_item_revision"] = 1
    item_id = uuid4()
    replaced = await _request(
        dependencies,
        "PUT",
        f"{base}/{item_id}",
        json=replacement,
    )

    assert created.status_code == 201, created.text
    assert created.json() == {"result": {"revision": None, "changes": []}}
    assert replaced.status_code == 200, replaced.text
    assert replaced.json() == {"result": {"revision": None, "changes": []}}
    assert [call[0] for call in dependencies.mutations.calls] == [
        f"create_{method_suffix}",
        f"replace_{method_suffix}",
    ]


@pytest.mark.asyncio
async def test_typed_memory_errors_have_stable_status_codes_and_safe_messages() -> None:
    competition_id = uuid4()
    missing_id = uuid4()
    stale_expected = uuid4()
    stale_actual = uuid4()
    missing = StubMemoryDependencies(competition_id=competition_id)
    stale = StubMemoryDependencies(
        competition_id=competition_id,
        mutation_error=StaleCanonicalRevisionError(
            competition_id,
            stale_expected,
            stale_actual,
        ),
    )
    projection = StubMemoryDependencies(
        competition_id=competition_id,
        retrieval_error=SearchProjectionHydrationError(
            uuid4(),
            MemoryKind.FACT,
            "sensitive storage detail",
        ),
    )
    base = f"/api/v1/memory/competitions/{competition_id}"

    not_found = await _request(
        missing,
        "GET",
        f"{base}/facts/versions/{missing_id}",
    )
    stale_write = await _request(
        stale,
        "POST",
        f"{base}/facts",
        json=_write_cases()[0][1],
    )
    inconsistent = await _request(
        projection,
        "POST",
        f"{base}/search",
        json={"revision_id": str(uuid4()), "query": {}},
    )

    assert not_found.status_code == 404
    assert not_found.json()["detail"]["code"] == "target_not_found"
    assert stale_write.status_code == 409
    assert stale_write.json()["detail"]["code"] == "stale_canonical_revision"
    assert inconsistent.status_code == 500
    assert inconsistent.json() == {
        "detail": {
            "code": "search_projection_inconsistent",
            "message": (
                "memory search projection is inconsistent with canonical memory"
            ),
        }
    }
    assert "sensitive storage detail" not in inconsistent.text


def test_openapi_contains_every_memory_resource_boundary() -> None:
    app = create_app(runtime_factory=runtime_factory())
    paths = set(app.openapi()["paths"])
    prefix = "/api/v1/memory/competitions/{competition_id}"

    assert {
        f"{prefix}/revisions/current",
        f"{prefix}/revisions",
        f"{prefix}/revisions/{{revision_id}}",
        f"{prefix}/search",
    }.issubset(paths)
    for resource in ("facts", "events", "storylines", "triggers", "context-notes"):
        assert f"{prefix}/{resource}" in paths
        assert f"{prefix}/{resource}/{{item_id}}" in paths
        assert f"{prefix}/{resource}/versions/{{version_id}}" in paths
        assert f"{prefix}/{resource}/{{item_id}}/history" in paths
