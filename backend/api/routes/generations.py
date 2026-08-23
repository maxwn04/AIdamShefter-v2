"""Polling-oriented generation HTTP routes."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, status

from backend.api.dependencies import get_generation_api_dependencies
from backend.api.schemas.generations import (
    AICallPageResponse,
    AICallResponse,
    ArtifactPageResponse,
    ArtifactResponse,
    ArtifactVersionPageResponse,
    ArtifactVersionResponse,
    GenerationDetailResponse,
    GenerationPageResponse,
    GenerationResponse,
    SubmitGenerationBody,
    SubmittedArticleResponse,
    ToolCallPageResponse,
    ToolCallResponse,
)
from backend.composition import GenerationDependencies
from backend.resources.reporting.ai_calls import (
    AICallQuery,
    AICallResourceNotFound,
    AICallStatus,
)
from backend.resources.reporting.artifact_versions import (
    ArtifactVersionQuery,
    ArtifactVersionResourceNotFound,
)
from backend.resources.reporting.artifacts import (
    ArtifactQuery,
    ArtifactResourceNotFound,
)
from backend.resources.reporting.generations import (
    GenerationKind,
    GenerationQuery,
    GenerationResourceNotFound,
    GenerationStatus,
)
from backend.resources.reporting.tool_calls import (
    ToolCallQuery,
    ToolCallResourceNotFound,
    ToolCallStatus,
)
from backend.services.generations import GenerationRequest, RerunGenerationRequest


router = APIRouter(
    prefix="/generations/competitions/{competition_id}",
    tags=["generations"],
)
GenerationApi = Annotated[
    GenerationDependencies,
    Depends(get_generation_api_dependencies),
]
PageLimit = Annotated[int, Query(ge=1, le=200)]
PageOffset = Annotated[int, Query(ge=0)]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=GenerationResponse)
def submit_generation(
    competition_id: UUID,
    body: SubmitGenerationBody,
    dependencies: GenerationApi,
) -> GenerationResponse:
    generation = dependencies.service.submit(
        GenerationRequest(
            generation_id=uuid4(),
            competition_id=competition_id,
            competition_season_id=body.competition_season_id,
            kind=body.kind,
            request_text=body.request_text,
            week_start=body.week_start,
            week_end=body.week_end,
            requested_primary_model=body.requested_primary_model,
            settings=body.settings,
        )
    )
    return GenerationResponse(generation=generation)


@router.post(
    "/{generation_id}/reruns",
    status_code=status.HTTP_201_CREATED,
    response_model=GenerationResponse,
)
def rerun_generation(
    generation_id: UUID,
    dependencies: GenerationApi,
) -> GenerationResponse:
    generation = dependencies.service.rerun(
        RerunGenerationRequest(
            source_generation_id=generation_id,
            generation_id=uuid4(),
        )
    )
    return GenerationResponse(generation=generation)


@router.get("", response_model=GenerationPageResponse)
def generation_history(
    dependencies: GenerationApi,
    competition_season_id: UUID | None = None,
    kind: GenerationKind | None = None,
    generation_status: Annotated[
        GenerationStatus | None,
        Query(alias="status"),
    ] = None,
    rerun_of_generation_id: UUID | None = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> GenerationPageResponse:
    page = dependencies.generations.list(
        GenerationQuery(
            competition_season_id=competition_season_id,
            kind=kind,
            status=generation_status,
            rerun_of_generation_id=rerun_of_generation_id,
            limit=limit,
            offset=offset,
        )
    )
    return GenerationPageResponse(page=page)


@router.get("/articles", response_model=GenerationPageResponse)
def article_history(
    dependencies: GenerationApi,
    competition_season_id: UUID | None = None,
    kind: GenerationKind | None = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> GenerationPageResponse:
    page = dependencies.generations.list(
        GenerationQuery(
            competition_season_id=competition_season_id,
            kind=kind,
            submitted_only=True,
            limit=limit,
            offset=offset,
        )
    )
    return GenerationPageResponse(page=page)


@router.get("/{generation_id}", response_model=GenerationDetailResponse)
def generation_detail(
    generation_id: UUID,
    dependencies: GenerationApi,
) -> GenerationDetailResponse:
    return GenerationDetailResponse(
        generation=dependencies.generations.get(generation_id)
    )


@router.get(
    "/{generation_id}/article",
    response_model=SubmittedArticleResponse,
)
def submitted_article(
    generation_id: UUID,
    dependencies: GenerationApi,
) -> SubmittedArticleResponse:
    generation = dependencies.generations.get(generation_id)
    version_id = generation.submitted_artifact_version_id
    if version_id is None:
        raise GenerationResourceNotFound("submitted_article", generation_id)
    version = dependencies.artifact_versions.get(version_id)
    _require_generation(
        version.generation_id,
        generation_id,
        "artifact_version",
        version.id,
    )
    artifact = dependencies.artifacts.get(version.artifact_id)
    _require_generation(
        artifact.generation_id,
        generation_id,
        "artifact",
        artifact.id,
    )
    return SubmittedArticleResponse(
        generation=generation,
        artifact=artifact,
        version=version,
    )


@router.get("/{generation_id}/ai-calls", response_model=AICallPageResponse)
def ai_call_history(
    generation_id: UUID,
    dependencies: GenerationApi,
    turn_number: Annotated[int | None, Query(ge=1)] = None,
    call_status: Annotated[AICallStatus | None, Query(alias="status")] = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> AICallPageResponse:
    page = dependencies.ai_calls.list(
        AICallQuery(
            generation_id=generation_id,
            turn_number=turn_number,
            status=call_status,
            limit=limit,
            offset=offset,
        )
    )
    return AICallPageResponse(page=page)


@router.get(
    "/{generation_id}/ai-calls/{ai_call_id}",
    response_model=AICallResponse,
)
def ai_call_detail(
    generation_id: UUID,
    ai_call_id: UUID,
    dependencies: GenerationApi,
) -> AICallResponse:
    ai_call = dependencies.ai_calls.get(ai_call_id)
    if ai_call.generation_id != generation_id:
        raise AICallResourceNotFound("ai_call", ai_call_id)
    return AICallResponse(ai_call=ai_call)


@router.get("/{generation_id}/tool-calls", response_model=ToolCallPageResponse)
def tool_call_history(
    generation_id: UUID,
    dependencies: GenerationApi,
    ai_call_id: UUID | None = None,
    call_status: Annotated[ToolCallStatus | None, Query(alias="status")] = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> ToolCallPageResponse:
    page = dependencies.tool_calls.list(
        ToolCallQuery(
            generation_id=generation_id,
            ai_call_id=ai_call_id,
            status=call_status,
            limit=limit,
            offset=offset,
        )
    )
    return ToolCallPageResponse(page=page)


@router.get(
    "/{generation_id}/tool-calls/{tool_call_id}",
    response_model=ToolCallResponse,
)
def tool_call_detail(
    generation_id: UUID,
    tool_call_id: UUID,
    dependencies: GenerationApi,
) -> ToolCallResponse:
    tool_call = dependencies.tool_calls.get(tool_call_id)
    if tool_call.generation_id != generation_id:
        raise ToolCallResourceNotFound("tool_call", tool_call_id)
    return ToolCallResponse(tool_call=tool_call)


@router.get("/{generation_id}/artifacts", response_model=ArtifactPageResponse)
def artifact_history(
    generation_id: UUID,
    dependencies: GenerationApi,
    finalized: bool | None = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> ArtifactPageResponse:
    page = dependencies.artifacts.list(
        ArtifactQuery(
            generation_id=generation_id,
            finalized=finalized,
            limit=limit,
            offset=offset,
        )
    )
    return ArtifactPageResponse(page=page)


@router.get(
    "/{generation_id}/artifacts/{artifact_id}",
    response_model=ArtifactResponse,
)
def artifact_detail(
    generation_id: UUID,
    artifact_id: UUID,
    dependencies: GenerationApi,
) -> ArtifactResponse:
    artifact = dependencies.artifacts.get(artifact_id)
    _require_generation(
        artifact.generation_id,
        generation_id,
        "artifact",
        artifact_id,
    )
    return ArtifactResponse(artifact=artifact)


@router.get(
    "/{generation_id}/artifacts/{artifact_id}/versions",
    response_model=ArtifactVersionPageResponse,
)
def artifact_version_history(
    generation_id: UUID,
    artifact_id: UUID,
    dependencies: GenerationApi,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> ArtifactVersionPageResponse:
    artifact = dependencies.artifacts.get(artifact_id)
    _require_generation(
        artifact.generation_id,
        generation_id,
        "artifact",
        artifact_id,
    )
    page = dependencies.artifact_versions.list(
        ArtifactVersionQuery(artifact_id=artifact_id, limit=limit, offset=offset)
    )
    return ArtifactVersionPageResponse(page=page)


@router.get(
    "/{generation_id}/artifacts/{artifact_id}/versions/{version_id}",
    response_model=ArtifactVersionResponse,
)
def artifact_version_detail(
    generation_id: UUID,
    artifact_id: UUID,
    version_id: UUID,
    dependencies: GenerationApi,
) -> ArtifactVersionResponse:
    version = dependencies.artifact_versions.get(version_id)
    if version.artifact_id != artifact_id or version.generation_id != generation_id:
        raise ArtifactVersionResourceNotFound("artifact_version", version_id)
    return ArtifactVersionResponse(version=version)


def _require_generation(
    actual_generation_id: UUID,
    expected_generation_id: UUID,
    resource_kind: str,
    resource_id: UUID,
) -> None:
    if actual_generation_id != expected_generation_id:
        if resource_kind == "artifact":
            raise ArtifactResourceNotFound(resource_kind, resource_id)
        raise ArtifactVersionResourceNotFound(resource_kind, resource_id)
