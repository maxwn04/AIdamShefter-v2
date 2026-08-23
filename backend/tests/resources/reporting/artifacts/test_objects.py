from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.resources.reporting.artifacts import ArtifactQuery, CreateArtifact


def test_artifact_identity_normalizes_media_type() -> None:
    command = CreateArtifact(
        generation_id=uuid4(),
        path="research/brief.md",
        media_type=" Text/Markdown ",
    )
    assert command.path == "research/brief.md"
    assert command.media_type == "text/markdown"


@pytest.mark.parametrize(
    "path",
    ["", "/article.md", "../article.md", "research//brief.md", "C:/article.md"],
)
def test_artifact_identity_rejects_unsafe_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        CreateArtifact(
            generation_id=uuid4(),
            path=path,
            media_type="text/markdown",
        )


def test_artifact_contracts_reject_invalid_media_and_paging() -> None:
    with pytest.raises(ValidationError, match="IANA media type"):
        CreateArtifact(
            generation_id=uuid4(),
            path="article.md",
            media_type="markdown",
        )
    with pytest.raises(ValidationError):
        ArtifactQuery(generation_id=uuid4(), limit=0)
    with pytest.raises(ValidationError):
        ArtifactQuery(generation_id=uuid4(), offset=-1)
