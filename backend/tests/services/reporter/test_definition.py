from __future__ import annotations

from backend.services.reporter import prepare_reporter_definition
from backend.services.reporter.runner.run_log import RunLog
from backend.services.reporter.runner.state import ArtifactStore, ProcedureState
from backend.services.reporter.runner.tools.context import ToolContext
from backend.services.reporter.runner.tools.procedure_tools import (
    PROCEDURE_TOOL_IMPLEMENTATION_VERSION,
    register_procedure_tools,
)
from backend.services.reporter.runner.tools.registry import ToolRegistry


def test_prepared_definition_matches_registered_execution_bundle() -> None:
    definition = prepare_reporter_definition(memory_enabled=True)
    registry = ToolRegistry()

    from backend.services.reporter.runner.tools.artifact_tools import (
        register_artifact_tools,
    )
    from backend.services.reporter.runner.tools.datalayer_tools import (
        register_datalayer_tools,
    )
    from backend.services.reporter.runner.tools.memory_tools import (
        register_memory_tools,
    )

    data = object()
    memory = object()
    register_artifact_tools(registry)
    register_procedure_tools(registry, definition.procedure_contents)
    register_datalayer_tools(registry, data)  # type: ignore[arg-type]
    register_memory_tools(
        registry,
        memory,  # type: ignore[arg-type]
        data,  # type: ignore[arg-type]
    )

    assert registry.tool_specs == [tool.definition for tool in definition.tools]
    assert registry.tool_implementation_versions == [
        (tool.name, tool.implementation_version) for tool in definition.tools
    ]
    assert PROCEDURE_TOOL_IMPLEMENTATION_VERSION == "3"
    assert {procedure.name for procedure in definition.procedures} == {
        "drafting",
        "research",
        "storyline",
        "verification",
    }


def test_definition_without_memory_omits_only_memory_tools() -> None:
    with_memory = prepare_reporter_definition(memory_enabled=True)
    without_memory = prepare_reporter_definition(memory_enabled=False)

    memory_names = {
        "search_memory",
        "propose_fact",
        "replace_fact",
        "propose_event",
        "replace_event",
        "propose_storyline",
        "replace_storyline",
        "propose_trigger",
        "replace_trigger",
        "propose_context_note",
        "replace_context_note",
    }
    assert {tool.name for tool in with_memory.tools} - {
        tool.name for tool in without_memory.tools
    } == memory_names


def test_registered_procedure_uses_prepared_content() -> None:
    registry = ToolRegistry()
    register_procedure_tools(registry, {"research": "frozen research"})
    registry.set_context(
        ToolContext(
            artifacts=ArtifactStore(),
            procedures=ProcedureState(),
            log=RunLog(),
        )
    )

    handler = registry.get_handler("load_procedure")

    assert handler is not None
    assert handler(name="research") == "frozen research"
