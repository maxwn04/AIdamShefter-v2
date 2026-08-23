import hashlib
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.resources.reporting.artifact_versions import (
    AppendArtifactVersion,
    ArtifactVersionQuery,
)


def test_append_contract_verifies_exact_utf8_content_hash() -> None:
    content = "touchdown — café"
    command = AppendArtifactVersion(
        artifact_id=uuid4(),
        content=content,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )
    assert command.content == content
    with pytest.raises(ValidationError, match="exact UTF-8"):
        AppendArtifactVersion(
            artifact_id=uuid4(),
            content=content,
            content_hash="0" * 64,
        )


def test_version_query_rejects_unsafe_pagination() -> None:
    with pytest.raises(ValidationError):
        ArtifactVersionQuery(artifact_id=uuid4(), limit=201)
    with pytest.raises(ValidationError):
        ArtifactVersionQuery(artifact_id=uuid4(), offset=-1)
