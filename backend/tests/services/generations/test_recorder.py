"""Tests for the durable generation AI-call recorder adapter."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest

from backend.resources.reporting.ai_calls import AICallManager
from backend.resources.reporting.artifact_versions import ArtifactVersionManager
from backend.resources.reporting.artifacts import ArtifactManager
from backend.resources.reporting.generations import GenerationManager
from backend.resources.reporting.tool_calls import ToolCallManager
from backend.services.generations import GenerationExecutionRecorder
from backend.services.reporter.runner.recording import (
    ArtifactMutation,
    GenerationProgress,
    ModelAttemptFinish,
    ModelAttemptStart,
    RecordedTokenUsage,
    ToolExecutionFinish,
    ToolExecutionStart,
)


class FakeAICallManager:
    def __init__(self) -> None:
        self.begun = []
        self.finished = []
        self.turns: dict[UUID, int] = {}

    def begin_ai_call(self, command):
        call_id = uuid4()
        self.begun.append(command)
        self.turns[call_id] = command.turn_number
        return SimpleNamespace(id=call_id)

    def finish_ai_call(self, command):
        self.finished.append(command)
        return SimpleNamespace(
            id=command.ai_call_id,
            turn_number=self.turns[command.ai_call_id],
            status=SimpleNamespace(value=command.status.value),
        )


class FakeToolCallManager:
    def __init__(self) -> None:
        self.begun = []
        self.finished = []

    def begin_tool_call(self, command):
        self.begun.append(command)
        return SimpleNamespace(id=uuid4())

    def finish_tool_call(self, command):
        self.finished.append(command)
        return SimpleNamespace(id=command.tool_call_id)


class FakeGenerationManager:
    def __init__(self) -> None:
        self.progress = []

    def update_progress(self, command):
        self.progress.append(command)
        return SimpleNamespace(id=command.generation_id)


class FakeArtifactManager:
    def __init__(self) -> None:
        self.created = []
        self.ids: dict[str, UUID] = {}

    def create_artifact(self, command):
        self.created.append(command)
        artifact_id = self.ids.setdefault(command.path, uuid4())
        return SimpleNamespace(
            id=artifact_id,
            generation_id=command.generation_id,
            path=command.path,
            media_type=command.media_type,
        )


class FakeArtifactVersionManager:
    def __init__(self, generation_id: UUID) -> None:
        self.generation_id = generation_id
        self.appended = []
        self.versions: dict[UUID, list[SimpleNamespace]] = {}

    def append_artifact_version(self, command):
        self.appended.append(command)
        versions = self.versions.setdefault(command.artifact_id, [])
        if (
            versions
            and versions[-1].content == command.content
            and versions[-1].content_hash == command.content_hash
        ):
            return versions[-1]
        version = SimpleNamespace(
            id=uuid4(),
            artifact_id=command.artifact_id,
            generation_id=self.generation_id,
            revision_number=len(versions) + 1,
            content=command.content,
            content_hash=command.content_hash,
            source_ai_call_id=command.source_ai_call_id,
            source_tool_call_id=command.source_tool_call_id,
        )
        versions.append(version)
        return version


def make_recorder(
    generation_id: UUID | None = None,
) -> tuple[
    GenerationExecutionRecorder,
    FakeAICallManager,
    FakeToolCallManager,
    FakeGenerationManager,
    FakeArtifactManager,
    FakeArtifactVersionManager,
]:
    resolved_generation_id = generation_id or uuid4()
    ai_calls = FakeAICallManager()
    tool_calls = FakeToolCallManager()
    generations = FakeGenerationManager()
    artifacts = FakeArtifactManager()
    artifact_versions = FakeArtifactVersionManager(resolved_generation_id)
    recorder = GenerationExecutionRecorder(
        resolved_generation_id,
        cast(AICallManager, ai_calls),
        cast(ToolCallManager, tool_calls),
        cast(GenerationManager, generations),
        cast(ArtifactManager, artifacts),
        cast(ArtifactVersionManager, artifact_versions),
    )
    return (
        recorder,
        ai_calls,
        tool_calls,
        generations,
        artifacts,
        artifact_versions,
    )


def test_recorder_maps_reporter_events_and_retains_success_identity() -> None:
    generation_id = uuid4()
    recorder, manager, _, _, _, _ = make_recorder(generation_id)
    attempt_id = recorder.begin_model_attempt(
        ModelAttemptStart(
            turn_number=2,
            requested_provider="openai",
            requested_model="openai/model",
            input_messages=({"role": "user", "content": "hello"},),
            tool_definitions=({"type": "function", "name": "lookup"},),
            request_parameters={"temperature": 0.2},
        )
    )
    recorder.finish_model_attempt(
        attempt_id,
        ModelAttemptFinish(
            status="succeeded",
            actual_provider="openai",
            actual_model="model",
            provider_response={"id": "response-1"},
            usage=RecordedTokenUsage(
                input_tokens=12,
                output_tokens=5,
                raw_provider_usage={"prompt_tokens": 12},
            ),
        ),
    )

    assert recorder.generation_id == generation_id
    assert manager.begun[0].generation_id == generation_id
    assert manager.begun[0].turn_number == 2
    assert manager.finished[0].usage.input_tokens == 12
    assert recorder.successful_ai_call_id(2) == attempt_id
    assert recorder.successful_ai_call_id(3) is None


def test_failed_attempt_does_not_become_successful_identity() -> None:
    recorder, _, _, _, _, _ = make_recorder()
    attempt_id = recorder.begin_model_attempt(
        ModelAttemptStart(
            turn_number=1,
            requested_provider=None,
            requested_model="model",
            input_messages=(),
            tool_definitions=(),
            request_parameters={},
        )
    )
    recorder.finish_model_attempt(
        attempt_id,
        ModelAttemptFinish(
            status="retryable_error",
            error={"type": "TimeoutError", "message": "timeout"},
        ),
    )

    assert recorder.successful_ai_call_id(1) is None


def test_recorder_maps_tool_execution_to_successful_turn_provenance() -> None:
    generation_id = uuid4()
    recorder, _, tool_calls, _, _, _ = make_recorder(generation_id)
    attempt_id = recorder.begin_model_attempt(
        ModelAttemptStart(
            turn_number=4,
            requested_provider="openai",
            requested_model="model",
            input_messages=(),
            tool_definitions=(),
            request_parameters={},
        )
    )
    recorder.finish_model_attempt(
        attempt_id,
        ModelAttemptFinish(
            status="succeeded",
            actual_model="model",
            provider_response={"choices": []},
        ),
    )

    execution_id = recorder.begin_tool_execution(
        ToolExecutionStart(
            turn_number=4,
            tool_ordinal=2,
            provider_tool_call_id="provider-call-2",
            tool_name="lookup",
            implementation_version="lookup-v3",
            arguments={"week": 8},
        )
    )
    recorder.finish_tool_execution(
        execution_id,
        ToolExecutionFinish(
            status="succeeded",
            result={"found": True},
            result_text='{"found": true}',
            metadata={"candidate_count": 3},
        ),
    )

    begun = tool_calls.begun[0]
    assert begun.generation_id == generation_id
    assert begun.ai_call_id == attempt_id
    assert begun.tool_ordinal == 2
    assert begun.provider_tool_call_id == "provider-call-2"
    assert begun.tool_name == "lookup"
    assert begun.implementation_version == "lookup-v3"
    assert begun.arguments == {"week": 8}
    finished = tool_calls.finished[0]
    assert finished.tool_call_id == execution_id
    assert finished.status.value == "succeeded"
    assert finished.result == {"found": True}
    assert finished.result_text == '{"found": true}'
    assert finished.metadata == {"candidate_count": 3}


def test_recorder_rejects_tools_without_a_successful_turn() -> None:
    recorder, _, tool_calls, _, _, _ = make_recorder()

    with pytest.raises(RuntimeError, match="successful AI call"):
        recorder.begin_tool_execution(
            ToolExecutionStart(
                turn_number=1,
                tool_ordinal=0,
                provider_tool_call_id=None,
                tool_name="lookup",
                implementation_version="v1",
                arguments={},
            )
        )

    assert tool_calls.begun == []


def test_recorder_deduplicates_identical_progress_checkpoints() -> None:
    generation_id = uuid4()
    recorder, _, _, generations, _, _ = make_recorder(generation_id)

    recorder.update_progress(
        GenerationProgress(current_turn=1, current_stage="running")
    )
    recorder.update_progress(
        GenerationProgress(current_turn=1, current_stage="running")
    )
    recorder.update_progress(
        GenerationProgress(current_turn=1, current_stage="research")
    )

    assert [
        (command.generation_id, command.current_turn, command.current_stage)
        for command in generations.progress
    ] == [
        (generation_id, 1, "running"),
        (generation_id, 1, "research"),
    ]


def test_recorder_persists_seed_and_tool_mutations_with_exact_provenance() -> None:
    generation_id = uuid4()
    recorder, _, _, _, artifacts, versions = make_recorder(generation_id)
    seed = ArtifactMutation(
        path="research_brief.md",
        media_type="text/markdown",
        content="# Brief",
        revision=1,
        content_hash="fd55350669a978d5a8cde0218d92baa5d6f8e1c9102f40cc42301a56543cc99d",
    )
    recorder.record_artifact_mutation(seed)

    attempt_id = recorder.begin_model_attempt(
        ModelAttemptStart(
            turn_number=1,
            requested_provider=None,
            requested_model="model",
            input_messages=(),
            tool_definitions=(),
            request_parameters={},
        )
    )
    recorder.finish_model_attempt(
        attempt_id,
        ModelAttemptFinish(
            status="succeeded",
            actual_model="model",
            provider_response={"choices": []},
        ),
    )
    execution_id = recorder.begin_tool_execution(
        ToolExecutionStart(
            turn_number=1,
            tool_ordinal=0,
            provider_tool_call_id="call-1",
            tool_name="edit_artifact",
            implementation_version="2",
            arguments={},
        )
    )
    edited = ArtifactMutation(
        path="research_brief.md",
        media_type="text/markdown",
        content="# Brief\n\nFact",
        revision=2,
        content_hash="08808033cd0b39693b096ed7cf4553f0186b76aae404c125b8ddb66b88680862",
        source_tool_call_id=execution_id,
    )
    version_id = recorder.record_artifact_mutation(edited)

    assert len(artifacts.created) == 2
    seed_command, edit_command = versions.appended
    assert seed_command.source_ai_call_id is None
    assert seed_command.source_tool_call_id is None
    assert edit_command.source_ai_call_id == attempt_id
    assert edit_command.source_tool_call_id == execution_id
    assert version_id == next(iter(versions.versions.values()))[-1].id


def test_recorder_returns_identical_version_and_rejects_revision_drift() -> None:
    recorder, _, _, _, _, versions = make_recorder()
    mutation = ArtifactMutation(
        path="article.md",
        media_type="text/markdown",
        content="same",
        revision=1,
        content_hash="0967115f2813a3541eaef77de9d9d5773f1c0c04314b0bbfe4ff3b3b1c55b5d5",
    )

    first = recorder.record_artifact_mutation(mutation)
    repeated = recorder.record_artifact_mutation(mutation)

    assert repeated == first
    assert len(next(iter(versions.versions.values()))) == 1

    drifted = ArtifactMutation(
        path="article.md",
        media_type="text/markdown",
        content="different",
        revision=3,
        content_hash="9d6f965ac832e40a5df6c06afe983e3b449c07b843ff51ce76204de05c690d11",
    )
    with pytest.raises(RuntimeError, match="does not match mutation"):
        recorder.record_artifact_mutation(drifted)
