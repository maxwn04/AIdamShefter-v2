"""Immutable generation input manifest construction and identity."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Annotated, Any, Literal, TypeAlias, cast
from uuid import UUID

from pydantic import AwareDatetime, Field, JsonValue, StringConstraints, model_validator

from backend.resources._contracts import ContractModel, NonBlankStr
from backend.resources.reporting.generations import GenerationKind


MANIFEST_SCHEMA_VERSION = 1

Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
PositiveInt = Annotated[int, Field(strict=True, ge=1)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveWeek = Annotated[int, Field(strict=True, ge=1, le=18)]
SafeName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$",
    ),
]


class GenerationRequestInput(ContractModel):
    kind: GenerationKind
    request_text: NonBlankStr
    resolved_settings: dict[str, JsonValue]


class DataSnapshotInput(ContractModel):
    data_snapshot_id: UUID
    snapshot_projection_version: NonBlankStr
    artifact_sha256: Sha256


class CanonicalMemoryInput(ContractModel):
    kind: Literal["canonical_revision"] = "canonical_revision"
    revision_id: UUID


class EvaluationArtifactMemoryInput(ContractModel):
    kind: Literal["evaluation_artifact"] = "evaluation_artifact"
    artifact_version_id: UUID
    source_generation_id: UUID


MemoryInput: TypeAlias = Annotated[
    CanonicalMemoryInput | EvaluationArtifactMemoryInput,
    Field(discriminator="kind"),
]


class ManifestCutoffs(ContractModel):
    domain_cutoff_week: PositiveWeek
    domain_cutoff_at: AwareDatetime
    knowledge_cutoff_at: AwareDatetime


class RetryPolicyInput(ContractModel):
    max_retries: NonNegativeInt
    base_delay_seconds: float = Field(gt=0)
    max_delay_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_delays(self) -> "RetryPolicyInput":
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max delay must be greater than or equal to base delay")
        return self


class ModelExecutionInput(ContractModel):
    requested_provider: NonBlankStr | None = None
    requested_model: NonBlankStr
    fallback_models: tuple[NonBlankStr, ...] = ()
    retry: RetryPolicyInput
    request_parameters: dict[str, JsonValue]

    @model_validator(mode="after")
    def validate_model_chain(self) -> "ModelExecutionInput":
        chain = (self.requested_model, *self.fallback_models)
        if len(chain) != len(set(chain)):
            raise ValueError("resolved model chain must not contain duplicates")
        return self


class RunnerExecutionInput(ContractModel):
    max_turns: PositiveInt
    procedure_history_mode: Literal["replace", "append"]


class ProcedureInput(ContractModel):
    name: SafeName
    content_sha256: Sha256


class ToolInput(ContractModel):
    name: SafeName
    definition: dict[str, JsonValue]
    implementation_version: SafeName

    @model_validator(mode="after")
    def validate_definition_name(self) -> "ToolInput":
        function = self.definition.get("function")
        definition_name = function.get("name") if isinstance(function, dict) else None
        if definition_name != self.name:
            raise ValueError("tool definition name must match tool input name")
        return self


class CodeRevisionInput(ContractModel):
    reporter_revision: NonBlankStr
    generation_revision: NonBlankStr


class GenerationManifestInput(ContractModel):
    generation: GenerationRequestInput
    data_snapshot: DataSnapshotInput
    memory_input: MemoryInput
    cutoffs: ManifestCutoffs
    model: ModelExecutionInput
    runner: RunnerExecutionInput
    system_prompt_sha256: Sha256
    procedures: tuple[ProcedureInput, ...]
    tools: tuple[ToolInput, ...]
    code: CodeRevisionInput

    @model_validator(mode="after")
    def validate_named_inputs(self) -> "GenerationManifestInput":
        procedure_names = [procedure.name for procedure in self.procedures]
        if not procedure_names:
            raise ValueError("generation manifest requires at least one procedure")
        if len(procedure_names) != len(set(procedure_names)):
            raise ValueError("procedure names must be unique")
        tool_names = [tool.name for tool in self.tools]
        if not tool_names:
            raise ValueError("generation manifest requires at least one tool")
        if len(tool_names) != len(set(tool_names)):
            raise ValueError("tool names must be unique")
        return self


@dataclass(frozen=True, slots=True)
class BuiltGenerationManifest:
    manifest: dict[str, JsonValue]
    schema_version: int
    canonical_bytes: bytes
    manifest_hash: str


def build_generation_manifest(
    inputs: GenerationManifestInput,
) -> BuiltGenerationManifest:
    """Build the complete immutable input seal for one generation."""
    procedures = sorted(inputs.procedures, key=lambda procedure: procedure.name)
    tool_definitions = [tool.definition for tool in inputs.tools]
    manifest = cast(
        dict[str, JsonValue],
        {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "generation": inputs.generation.model_dump(mode="json"),
            "data_snapshot": inputs.data_snapshot.model_dump(mode="json"),
            "memory_input": inputs.memory_input.model_dump(mode="json"),
            "cutoffs": inputs.cutoffs.model_dump(mode="json"),
            "model": inputs.model.model_dump(mode="json"),
            "runner": inputs.runner.model_dump(mode="json"),
            "assets": {
                "system_prompt_sha256": inputs.system_prompt_sha256,
                "procedures": [
                    procedure.model_dump(mode="json") for procedure in procedures
                ],
            },
            "tools": {
                "schema_bundle_sha256": canonical_json_sha256(tool_definitions),
                "implementations": [
                    {
                        "name": tool.name,
                        "version": tool.implementation_version,
                    }
                    for tool in inputs.tools
                ],
            },
            "code": inputs.code.model_dump(mode="json"),
        },
    )
    encoded = canonical_json_bytes(manifest)
    return BuiltGenerationManifest(
        manifest=manifest,
        schema_version=MANIFEST_SCHEMA_VERSION,
        canonical_bytes=encoded,
        manifest_hash=hashlib.sha256(encoded).hexdigest(),
    )


def canonical_json_bytes(value: JsonValue) -> bytes:
    """Encode a JSON value with the generation manifest's stable rules."""
    _validate_json_value(value)
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_json_sha256(value: JsonValue) -> str:
    """Return the lowercase SHA-256 of canonical generation JSON."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON numbers must be finite")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical JSON object keys must be strings")
        for item in value.values():
            _validate_json_value(item)
        return
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "BuiltGenerationManifest",
    "CanonicalMemoryInput",
    "CodeRevisionInput",
    "DataSnapshotInput",
    "EvaluationArtifactMemoryInput",
    "GenerationManifestInput",
    "GenerationRequestInput",
    "ManifestCutoffs",
    "ModelExecutionInput",
    "ProcedureInput",
    "RetryPolicyInput",
    "RunnerExecutionInput",
    "ToolInput",
    "build_generation_manifest",
    "canonical_json_bytes",
    "canonical_json_sha256",
]
