from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.resources.reporting.generations import (
    CreateGeneration,
    GenerationKind,
    GenerationQuery,
    StartGeneration,
)


def _create_values() -> dict[str, object]:
    return {
        "generation_id": uuid4(),
        "competition_season_id": uuid4(),
        "kind": GenerationKind.LIVE,
        "request_text": "write the recap",
        "week_start": 4,
        "week_end": 8,
        "requested_primary_model": "test-model",
        "settings": {"temperature": 0.2, "enabled": True},
    }


def test_create_contract_validates_coverage_and_workspace_shape() -> None:
    command = CreateGeneration.model_validate(_create_values())
    assert command.week_start == 4
    with pytest.raises(ValidationError, match="provided together"):
        CreateGeneration.model_validate({**_create_values(), "week_end": None})
    with pytest.raises(ValidationError, match="cannot be after"):
        CreateGeneration.model_validate(
            {**_create_values(), "week_start": 9, "week_end": 8}
        )
    with pytest.raises(ValidationError, match="sequence number"):
        CreateGeneration.model_validate(
            {**_create_values(), "evaluation_workspace_id": uuid4()}
        )


def test_start_contract_requires_one_complete_memory_input_and_manifest() -> None:
    values = {
        "generation_id": uuid4(),
        "data_snapshot_id": uuid4(),
        "knowledge_cutoff_at": datetime.now(UTC),
        "input_manifest": {"schema": 1},
        "manifest_schema_version": 1,
        "manifest_hash": "a" * 64,
    }
    canonical = StartGeneration.model_validate(
        {**values, "input_memory_revision_id": uuid4()}
    )
    assert canonical.input_memory_artifact_version_id is None
    with pytest.raises(ValidationError, match="exactly one"):
        StartGeneration.model_validate(values)
    with pytest.raises(ValidationError, match="both artifact IDs"):
        StartGeneration.model_validate(
            {**values, "input_memory_artifact_version_id": uuid4()}
        )
    with pytest.raises(ValidationError, match="non-empty"):
        StartGeneration.model_validate(
            {**values, "input_manifest": {}, "input_memory_revision_id": uuid4()}
        )


def test_generation_query_rejects_unsafe_pagination() -> None:
    assert GenerationQuery().limit == 50
    with pytest.raises(ValidationError):
        GenerationQuery(limit=0)
    with pytest.raises(ValidationError):
        GenerationQuery(offset=-1)
