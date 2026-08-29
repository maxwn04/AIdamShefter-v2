"""Golden tests for immutable generation input manifests."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID

import pytest

from backend.resources.reporting.generations import GenerationKind
from backend.services.generations import (
    CanonicalMemoryInput,
    CodeRevisionInput,
    DataSnapshotInput,
    DataSnapshotSeasonInput,
    EvaluationArtifactMemoryInput,
    GenerationManifestInput,
    GenerationRequestInput,
    ManifestCutoffs,
    ModelExecutionInput,
    ProcedureInput,
    RetryPolicyInput,
    RunnerExecutionInput,
    SnapshotPreparationInput,
    SnapshotRefreshReceiptInput,
    ToolInput,
    build_generation_manifest,
    canonical_json_bytes,
)
from backend.services.reporter.runner.tools.artifact_tools import (
    ARTIFACT_TOOL_IMPLEMENTATION_VERSION,
    ARTIFACT_TOOL_SPECS,
)
from backend.services.reporter.runner.tools.memory_tools import (
    MEMORY_TOOL_IMPLEMENTATION_VERSION,
    MEMORY_TOOL_SPECS,
)


def _uuid(value: int) -> UUID:
    return UUID(int=value)


def _submit_tool() -> ToolInput:
    spec = next(
        spec
        for spec in ARTIFACT_TOOL_SPECS
        if spec["function"]["name"] == "submit_artifact"
    )
    return ToolInput(
        name="submit_artifact",
        definition=spec,
        implementation_version=ARTIFACT_TOOL_IMPLEMENTATION_VERSION,
    )


def _lookup_tool() -> ToolInput:
    return ToolInput(
        name="lookup",
        definition={
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "Look up café facts.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        implementation_version="lookup-v1",
    )


def _inputs(
    *,
    memory_input: CanonicalMemoryInput | EvaluationArtifactMemoryInput | None = None,
) -> GenerationManifestInput:
    return GenerationManifestInput(
        generation=GenerationRequestInput(
            kind=GenerationKind.LIVE,
            request_text="Write a lively recap.",
            resolved_settings={"temperature": 0.25, "weeks": [7, 8]},
        ),
        data_snapshot=DataSnapshotInput(
            data_snapshot_id=_uuid(1),
            primary_competition_season_id=_uuid(10),
            snapshot_projection_version="snapshot-v3",
            artifact_sha256="a" * 64,
            input_revision="f" * 64,
            included_seasons=(
                DataSnapshotSeasonInput(
                    competition_season_id=_uuid(10),
                    sleeper_league_id="league-2026",
                    season_year=2026,
                    sequence_number=2,
                    role="primary",
                    through_week=8,
                ),
            ),
            preparation=SnapshotPreparationInput(mode="live"),
        ),
        memory_input=memory_input or CanonicalMemoryInput(revision_id=_uuid(2)),
        cutoffs=ManifestCutoffs(
            domain_cutoff_week=8,
            domain_cutoff_at=datetime(2026, 10, 28, 7, tzinfo=UTC),
            knowledge_cutoff_at=datetime(2026, 10, 29, 19, 30, tzinfo=UTC),
        ),
        model=ModelExecutionInput(
            requested_provider="openai",
            requested_model="gpt-primary",
            fallback_models=("gpt-fallback",),
            retry=RetryPolicyInput(
                max_retries=2,
                base_delay_seconds=0.5,
                max_delay_seconds=4.0,
            ),
            request_parameters={"reasoning_effort": "none"},
        ),
        runner=RunnerExecutionInput(
            max_turns=60,
            procedure_history_mode="replace",
        ),
        system_prompt_sha256="b" * 64,
        procedures=(
            ProcedureInput(name="verification", content_sha256="d" * 64),
            ProcedureInput(name="research", content_sha256="c" * 64),
        ),
        tools=(_submit_tool(), _lookup_tool()),
        code=CodeRevisionInput(
            reporter_revision="reporter-5a",
            generation_revision="generation-5a",
        ),
    )


def test_canonical_json_has_a_locked_utf8_vector() -> None:
    value = {"z": [3, 2, 1], "a": {"café": True, "n": 1.0}}

    assert canonical_json_bytes(value) == (
        b'{"a":{"caf\xc3\xa9":true,"n":1.0},"z":[3,2,1]}'
    )


def test_manifest_has_a_locked_schema_and_hash() -> None:
    built = build_generation_manifest(_inputs())

    assert built.schema_version == 2
    assert built.manifest["schema_version"] == 2
    assert built.manifest_hash == (
        "e98a1845a3f3eae19b20c8d6804c287f10dcd6fdf516a3035fd4b777f2302556"
    )
    assert built.canonical_bytes.decode("utf-8").startswith(
        '{"assets":{"procedures":[{"content_sha256":"'
    )
    procedure_names = [
        procedure["name"] for procedure in built.manifest["assets"]["procedures"]
    ]
    assert procedure_names == ["research", "verification"]


def test_mapping_order_does_not_change_manifest_identity() -> None:
    inputs = _inputs()
    reversed_settings = dict(reversed(inputs.generation.resolved_settings.items()))
    reordered = inputs.model_copy(
        update={
            "generation": inputs.generation.model_copy(
                update={"resolved_settings": reversed_settings}
            )
        }
    )

    assert build_generation_manifest(inputs) == build_generation_manifest(reordered)


def test_snapshot_revision_coverage_and_receipts_change_manifest_identity() -> None:
    inputs = _inputs()
    history = DataSnapshotSeasonInput(
        competition_season_id=_uuid(9),
        sleeper_league_id="league-2025",
        season_year=2025,
        sequence_number=1,
        role="history",
        through_week=18,
    )
    primary = inputs.data_snapshot.included_seasons[0]
    receipt = SnapshotRefreshReceiptInput(
        claim_id=_uuid(30),
        competition_season_id=primary.competition_season_id,
        through_week=primary.through_week,
        refresh_run_id=_uuid(31),
        status="succeeded",
        disposition="claimed",
    )
    changed_coverage = inputs.model_copy(
        update={
            "data_snapshot": inputs.data_snapshot.model_copy(
                update={"included_seasons": (history, primary)}
            )
        }
    )
    changed_revision = inputs.model_copy(
        update={
            "data_snapshot": inputs.data_snapshot.model_copy(
                update={"input_revision": "e" * 64}
            )
        }
    )
    changed_receipts = inputs.model_copy(
        update={
            "data_snapshot": inputs.data_snapshot.model_copy(
                update={
                    "preparation": SnapshotPreparationInput(
                        mode="live",
                        refresh_receipts=(receipt,),
                    )
                }
            )
        }
    )

    original = build_generation_manifest(inputs).manifest_hash
    assert build_generation_manifest(changed_coverage).manifest_hash != original
    assert build_generation_manifest(changed_revision).manifest_hash != original
    assert build_generation_manifest(changed_receipts).manifest_hash != original


def test_snapshot_coverage_rejects_invalid_order_primary_and_receipts() -> None:
    primary = _inputs().data_snapshot.included_seasons[0]
    history = DataSnapshotSeasonInput(
        competition_season_id=_uuid(9),
        sleeper_league_id="league-2025",
        season_year=2025,
        sequence_number=1,
        role="history",
        through_week=18,
    )
    with pytest.raises(ValueError, match="oldest to primary"):
        DataSnapshotInput(
            data_snapshot_id=_uuid(1),
            primary_competition_season_id=primary.competition_season_id,
            snapshot_projection_version="3",
            artifact_sha256="a" * 64,
            input_revision="f" * 64,
            included_seasons=(primary, history),
            preparation=SnapshotPreparationInput(mode="live"),
        )
    with pytest.raises(ValueError, match="match the snapshot primary"):
        DataSnapshotInput(
            data_snapshot_id=_uuid(1),
            primary_competition_season_id=_uuid(99),
            snapshot_projection_version="3",
            artifact_sha256="a" * 64,
            input_revision="f" * 64,
            included_seasons=(primary,),
            preparation=SnapshotPreparationInput(mode="live"),
        )
    with pytest.raises(ValueError, match="match an included season and cutoff"):
        DataSnapshotInput(
            data_snapshot_id=_uuid(1),
            primary_competition_season_id=primary.competition_season_id,
            snapshot_projection_version="3",
            artifact_sha256="a" * 64,
            input_revision="f" * 64,
            included_seasons=(primary,),
            preparation=SnapshotPreparationInput(
                mode="live",
                refresh_receipts=(
                    SnapshotRefreshReceiptInput(
                        claim_id=_uuid(30),
                        competition_season_id=primary.competition_season_id,
                        through_week=7,
                        refresh_run_id=_uuid(31),
                        status="failed",
                        disposition="joined",
                    ),
                ),
            ),
        )


def test_snapshot_coverage_rejects_missing_and_duplicate_seasons() -> None:
    primary = _inputs().data_snapshot.included_seasons[0]
    with pytest.raises(ValueError, match="requires included season coverage"):
        DataSnapshotInput(
            data_snapshot_id=_uuid(1),
            primary_competition_season_id=primary.competition_season_id,
            snapshot_projection_version="3",
            artifact_sha256="a" * 64,
            input_revision="f" * 64,
            included_seasons=(),
            preparation=SnapshotPreparationInput(mode="live"),
        )
    with pytest.raises(ValueError, match="competition seasons must be unique"):
        DataSnapshotInput(
            data_snapshot_id=_uuid(1),
            primary_competition_season_id=primary.competition_season_id,
            snapshot_projection_version="3",
            artifact_sha256="a" * 64,
            input_revision="f" * 64,
            included_seasons=(primary, primary),
            preparation=SnapshotPreparationInput(mode="live"),
        )


def test_ordered_tool_bundle_changes_manifest_identity() -> None:
    inputs = _inputs()
    reordered = inputs.model_copy(update={"tools": tuple(reversed(inputs.tools))})

    original = build_generation_manifest(inputs)
    changed = build_generation_manifest(reordered)

    assert original.manifest_hash != changed.manifest_hash
    assert original.manifest["tools"]["schema_bundle_sha256"] != (
        changed.manifest["tools"]["schema_bundle_sha256"]
    )


@pytest.mark.parametrize(
    "field",
    ["settings", "prompt", "procedure", "tool_schema", "tool_version", "code"],
)
def test_every_versioned_input_changes_manifest_identity(field: str) -> None:
    inputs = _inputs()
    if field == "settings":
        generation = inputs.generation.model_copy(
            update={"resolved_settings": {"temperature": 0.5, "weeks": [7, 8]}}
        )
        changed = inputs.model_copy(update={"generation": generation})
    elif field == "prompt":
        changed = inputs.model_copy(update={"system_prompt_sha256": "e" * 64})
    elif field == "procedure":
        procedures = list(inputs.procedures)
        procedures[0] = procedures[0].model_copy(
            update={"content_sha256": "e" * 64}
        )
        changed = inputs.model_copy(update={"procedures": tuple(procedures)})
    elif field == "tool_schema":
        definition = deepcopy(inputs.tools[0].definition)
        definition["function"]["description"] = "Changed submission contract."
        tool = inputs.tools[0].model_copy(update={"definition": definition})
        changed = inputs.model_copy(update={"tools": (tool, *inputs.tools[1:])})
    elif field == "tool_version":
        tool = inputs.tools[0].model_copy(update={"implementation_version": "3"})
        changed = inputs.model_copy(update={"tools": (tool, *inputs.tools[1:])})
    else:
        code = inputs.code.model_copy(update={"reporter_revision": "reporter-next"})
        changed = inputs.model_copy(update={"code": code})

    assert build_generation_manifest(inputs).manifest_hash != (
        build_generation_manifest(changed).manifest_hash
    )


def test_memory_input_variants_are_explicit() -> None:
    live = build_generation_manifest(_inputs())
    evaluation = build_generation_manifest(
        _inputs(
            memory_input=EvaluationArtifactMemoryInput(
                artifact_version_id=_uuid(3),
                source_generation_id=_uuid(4),
            )
        )
    )

    assert live.manifest["memory_input"]["kind"] == "canonical_revision"
    assert evaluation.manifest["memory_input"]["kind"] == "evaluation_artifact"
    assert live.manifest_hash != evaluation.manifest_hash


def test_week_scoped_manifest_allows_no_instant_domain_cutoff() -> None:
    inputs = _inputs()
    inputs = inputs.model_copy(
        update={
            "cutoffs": inputs.cutoffs.model_copy(
                update={"domain_cutoff_at": None}
            )
        }
    )

    built = build_generation_manifest(inputs)

    assert built.manifest["cutoffs"]["domain_cutoff_at"] is None


def test_manifest_is_input_only_and_submit_schema_is_path_generic() -> None:
    inputs = _inputs()
    built = build_generation_manifest(inputs)
    serialized = built.canonical_bytes.decode("utf-8")
    submit_parameters = inputs.tools[0].definition["function"]["parameters"]

    assert "enum" not in submit_parameters["properties"]["path"]
    assert "submitted_artifact_version_id" not in serialized
    assert "submitted_path" not in serialized
    assert "article.md" not in serialized

    fixed_path_definition = deepcopy(inputs.tools[0].definition)
    fixed_path_definition["function"]["parameters"]["properties"]["path"][
        "enum"
    ] = ["article.md"]
    fixed_path_tool = inputs.tools[0].model_copy(
        update={"definition": fixed_path_definition}
    )
    fixed_path = inputs.model_copy(
        update={"tools": (fixed_path_tool, *inputs.tools[1:])}
    )
    assert built.manifest_hash != build_generation_manifest(fixed_path).manifest_hash


def test_semantic_memory_tool_bundle_is_manifest_safe_and_versioned() -> None:
    memory_tools = tuple(
        ToolInput(
            name=spec["function"]["name"],
            definition=spec,
            implementation_version=MEMORY_TOOL_IMPLEMENTATION_VERSION,
        )
        for spec in MEMORY_TOOL_SPECS
    )
    inputs = _inputs().model_copy(update={"tools": memory_tools})

    built = build_generation_manifest(inputs)

    names = [tool["name"] for tool in built.manifest["tools"]["implementations"]]
    assert names == [
        "search_memory",
        "save_memory_event",
        "upsert_storyline_memory_card",
        "save_storyline_trigger",
        "save_team_context",
        "save_league_note",
    ]
    assert "search_story_memory" not in names
    assert built.manifest["tools"]["schema_bundle_sha256"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_canonical_json_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        canonical_json_bytes({"value": value})
