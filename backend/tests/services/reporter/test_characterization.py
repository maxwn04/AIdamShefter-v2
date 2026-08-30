"""Side-by-side characterization of legacy and copied reporter behavior."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from backend.services.reporter.config import ReportConfig, TimeRange, ToneControls
from backend.services.reporter.generator import (
    _build_system_prompt as copied_system_prompt,
)
from backend.services.reporter.generator import (
    _build_user_message as copied_user_message,
)
from backend.services.reporter.generator import generate_article as copied_generate
from backend.services.reporter.runner.models import ToolCall as CopiedToolCall
from backend.services.reporter.runner.schemas import (
    ArtifactSnapshot,
    ReporterOutput,
)
from backend.services.reporter.runner.tools.artifact_tools import (
    ARTIFACT_TOOL_SPECS as COPIED_ARTIFACT_TOOLS,
)
from backend.services.reporter.runner.tools.brief_tools import (
    BRIEF_TOOL_SPECS as COPIED_BRIEF_TOOLS,
)
from backend.services.reporter.runner.tools.memory_tools import (
    MEMORY_TOOL_SPECS as COPIED_MEMORY_TOOLS,
)
from backend.services.reporter.runner.tools.procedure_tools import (
    PROCEDURE_TOOL_SPECS as COPIED_PROCEDURE_TOOLS,
)
from reporter_v2.config import ReportConfig as LegacyReportConfig
from reporter_v2.runner.article_generator import (
    _build_system_prompt as legacy_system_prompt,
)
from reporter_v2.runner.article_generator import (
    _build_user_message as legacy_user_message,
)
from reporter_v2.runner.article_generator import generate_article as legacy_generate
from reporter_v2.runner.schemas import (
    ArticleOutput as LegacyArticleOutput,
)
from reporter_v2.runner.tools.article_tools import (
    ARTICLE_TOOL_SPECS as LEGACY_ARTICLE_TOOLS,
)
from reporter_v2.runner.tools.brief_tools import (
    BRIEF_TOOL_SPECS as LEGACY_BRIEF_TOOLS,
)
from reporter_v2.runner.tools.procedure_tools import (
    PROCEDURE_TOOL_SPECS as LEGACY_PROCEDURE_TOOLS,
)


ROOT = Path(__file__).parents[4]


class DualLeagueData:
    """Small fake satisfying both the legacy and frozen generator seams."""

    league_id = "league_123"
    effective_week = 8
    _query_conn = None

    def run_sql(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        *,
        limit: int = 200,
    ) -> dict[str, Any]:
        del params, limit
        if "FROM leagues" in query:
            return {
                "columns": ["league_id", "name"],
                "rows": [[self.league_id, ""]],
                "row_count": 1,
            }
        return {"columns": [], "rows": [], "row_count": 0}


class CopiedScriptedCompletion:
    def __init__(self) -> None:
        self.responses = [
            _response(
                CopiedToolCall(
                    id="fact",
                    name="save_fact",
                    arguments={
                        "id": "fact_taco_win",
                        "claim_text": "Taco won.",
                        "data_refs": ["test_fixture"],
                    },
                )
            ),
            _response(
                CopiedToolCall(
                    id="create",
                    name="create_artifact",
                    arguments={
                        "path": "article.md",
                        "content": "# Week 8\n\nTaco won.",
                    },
                )
            ),
            _response(
                CopiedToolCall(
                    id="submit",
                    name="submit_artifact",
                    arguments={"path": "article.md", "expected_revision": 1},
                )
            ),
        ]

    async def __call__(self, **kwargs: Any) -> Any:
        del kwargs
        return self.responses.pop(0)


class LegacyScriptedCompletion:
    def __init__(self) -> None:
        self.responses = [
            _response(
                CopiedToolCall(
                    id="write",
                    name="write_section",
                    arguments={"name": "main", "content": "# Week 8\n\nTaco won."},
                )
            ),
            _response(
                CopiedToolCall(
                    id="submit",
                    name="submit_article",
                    arguments={},
                )
            ),
        ]

    async def __call__(self, **kwargs: Any) -> Any:
        del kwargs
        return self.responses.pop(0)


def _response(call: CopiedToolCall) -> Any:
    raw_call = SimpleNamespace(
        id=call.id,
        function=SimpleNamespace(
            name=call.name,
            arguments=json.dumps(call.arguments),
        ),
    )
    message = SimpleNamespace(content=None, tool_calls=[raw_call])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _tool_names(output: Any) -> list[str]:
    return [
        entry["data"]["tool_name"]
        for entry in output.run_log_entries
        if entry["event_type"] == "tool_call"
    ]


def test_public_config_matches_legacy_and_artifact_schemas_diverge() -> None:
    config = ReportConfig(
        time_range=TimeRange.range(7, 8),
        focus_hints=["playoff race"],
        tone=ToneControls(snark_level=2, hype_level=3, seriousness=1),
    ).with_bias(favored=["Team Taco"], intensity=2)

    assert config.model_dump(mode="json") == LegacyReportConfig.model_validate(
        config.model_dump(mode="json")
    ).model_dump(mode="json")
    assert ReportConfig.model_json_schema() == LegacyReportConfig.model_json_schema()
    assert ReporterOutput.model_json_schema() != LegacyArticleOutput.model_json_schema()
    assert set(ArtifactSnapshot.model_json_schema()["properties"]) == {
        "path",
        "media_type",
        "content",
        "revision",
        "content_hash",
    }
    assert set(ReporterOutput.model_json_schema()["properties"]) == {
        "submitted_path",
        "artifacts",
        "research_brief",
        "run_log_summary",
        "run_log_entries",
        "generated_at",
    }


def test_reporter_contracts_keep_only_deliberate_platform_divergences() -> None:
    config = ReportConfig.for_week(
        8,
        voice="deadpan beat writer",
        snark_level=2,
        focus_hints=["bench disasters"],
        custom_instructions="End with one clean callback.",
    )

    copied_message = copied_user_message(config)
    legacy_message = legacy_user_message(
        LegacyReportConfig.model_validate(config.model_dump(mode="json"))
    )
    assert copied_message != legacy_message
    assert "unmet editorial goal" in copied_message
    assert "not as a fixed phase or progress marker" in copied_message
    assert "smallest tool result" in copied_message
    assert copied_system_prompt() != legacy_system_prompt()
    assert "research_brief.md" in copied_system_prompt()
    assert "submit_artifact" in copied_system_prompt()

    copied_artifact_names = [
        spec["function"]["name"] for spec in COPIED_ARTIFACT_TOOLS
    ]
    legacy_artifact_names = {
        spec["function"]["name"]
        for spec in (*LEGACY_BRIEF_TOOLS, *LEGACY_ARTICLE_TOOLS)
    }
    assert copied_artifact_names == [
        "list_artifacts",
        "read_artifact",
        "create_artifact",
        "edit_artifact",
        "submit_artifact",
    ]
    assert set(copied_artifact_names).isdisjoint(legacy_artifact_names)
    assert [spec["function"]["name"] for spec in COPIED_BRIEF_TOOLS] == [
        "save_fact",
        "save_memory_callback",
        "save_storyline",
        "set_outline",
        "read_brief",
    ]
    assert COPIED_PROCEDURE_TOOLS != LEGACY_PROCEDURE_TOOLS
    assert "goal-oriented editorial guidance" in COPIED_PROCEDURE_TOOLS[0]["function"][
        "description"
    ]
    assert [spec["function"]["name"] for spec in COPIED_MEMORY_TOOLS] == [
        "search_memory",
        "save_memory_event",
        "upsert_storyline_memory_card",
        "save_storyline_trigger",
        "save_team_context",
        "save_league_note",
    ]


def test_prompt_and_procedure_assets_document_intentional_artifact_divergence() -> None:
    legacy = ROOT / "reporter_v2"
    copied = ROOT / "backend" / "services" / "reporter"

    expected_markers = {
        "prompts/system.md": "search_memory",
        "procedures/research.md": "search_memory",
        "procedures/storyline.md": "save_storyline",
        "procedures/drafting.md": "create_artifact",
        "procedures/verification.md": "submit_artifact",
    }
    flexibility_markers = {
        "prompts/system.md": "These goals are not phases",
        "procedures/research.md": "# Goal: Establish A Trustworthy Evidence Base",
        "procedures/storyline.md": "# Goal: Find The Article's Meaning",
        "procedures/drafting.md": "# Goal: Turn Verified Material Into A Compelling Article",
        "procedures/verification.md": "# Goal: Earn Publication Confidence",
    }
    for relative_path, marker in expected_markers.items():
        copied_text = (copied / relative_path).read_text(encoding="utf-8")
        legacy_text = (legacy / relative_path).read_text(encoding="utf-8")
        assert copied_text != legacy_text
        assert marker in copied_text
        assert flexibility_markers[relative_path] in copied_text

    system_prompt = (copied / "prompts/system.md").read_text(encoding="utf-8")
    assert "## Guidance Library" in system_prompt
    assert all(
        f"`{name}` supports" in system_prompt
        for name in ("research", "storyline", "drafting", "verification")
    )
    assert "## Article Quality" in system_prompt
    assert "materially improve factual confidence" in system_prompt
    assert "Search by editorial intent" in system_prompt
    assert "semantic leads, not storage identity or proof" in system_prompt
    assert "initial narrative leads" in system_prompt
    assert "Do not call `search_memory` merely to rediscover" in system_prompt
    assert "runtime may supply an `automatic_reporter_memory`" in system_prompt
    assert "They may be loaded in any order, combined, revisited" in system_prompt
    assert "one continuity question per call" in system_prompt
    assert "inclusive week bounds" in system_prompt
    assert "It does not create or update durable storyline cards" in system_prompt

    research = (copied / "procedures/research.md").read_text(encoding="utf-8")
    assert "Begin with any automatically recalled" in research
    assert "use `search_memory` only when a concrete" in research
    assert "optional targeted retrieval" in research
    assert "Do not repeat the automatic prelude" in research
    assert "prefer 5-8 focused semantic results" in research.lower()
    assert "Canonical memory identifiers are intentionally unavailable" in research
    assert "Never pack unrelated teams" in research
    assert "inclusive `week_from` / `week_to`" in research
    assert "it does not create or update durable storyline cards" in research

    storyline = (copied / "procedures/storyline.md").read_text(encoding="utf-8")
    assert "it does not persist the storyline card itself" in storyline


def test_generator_preserves_article_result_across_artifact_contract_divergence() -> None:
    data = DualLeagueData()
    copied = asyncio.run(
        copied_generate(
            data,  # type: ignore[arg-type]
            ReportConfig.for_week(8),
            complete=CopiedScriptedCompletion(),
        )
    )
    legacy = asyncio.run(
        legacy_generate(
            data,  # type: ignore[arg-type]
            LegacyReportConfig.for_week(8),
            complete=LegacyScriptedCompletion(),
        )
    )

    assert copied.article == legacy.article == "# Week 8\n\nTaco won."
    assert copied.submitted_path == "article.md"
    assert [artifact.path for artifact in copied.artifacts] == [
        "article.md",
        "research_brief.md",
    ]
    assert copied.artifacts[0].revision == 1
    assert "# Research Brief" in copied.artifacts[1].content
    assert copied.run_log_summary["submitted"] is True
    assert legacy.run_log_summary["submitted"] is True
    assert _tool_names(copied) == [
        "save_fact",
        "create_artifact",
        "submit_artifact",
    ]
    assert _tool_names(legacy) == ["write_section", "submit_article"]
