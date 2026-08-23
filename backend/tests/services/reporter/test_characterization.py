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
    Article,
    ArticleOutput,
    ReportBrief,
)
from backend.services.reporter.runner.tools.article_tools import (
    ARTICLE_TOOL_SPECS as COPIED_ARTICLE_TOOLS,
)
from backend.services.reporter.runner.tools.brief_tools import (
    BRIEF_TOOL_SPECS as COPIED_BRIEF_TOOLS,
)
from backend.services.reporter.runner.tools.persistent_tools import (
    PERSISTENT_TOOL_SPECS as COPIED_PERSISTENT_TOOLS,
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
    Article as LegacyArticle,
)
from reporter_v2.runner.schemas import (
    ArticleOutput as LegacyArticleOutput,
)
from reporter_v2.runner.schemas import (
    ReportBrief as LegacyReportBrief,
)
from reporter_v2.runner.tools.article_tools import (
    ARTICLE_TOOL_SPECS as LEGACY_ARTICLE_TOOLS,
)
from reporter_v2.runner.tools.brief_tools import (
    BRIEF_TOOL_SPECS as LEGACY_BRIEF_TOOLS,
)
from reporter_v2.runner.tools.persistent_tools import (
    PERSISTENT_TOOL_SPECS as LEGACY_PERSISTENT_TOOLS,
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


class ScriptedCompletion:
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


def _stable_output(output: Any) -> dict[str, Any]:
    summary = dict(output.run_log_summary)
    summary.pop("session_id", None)
    entries = []
    for entry in output.run_log_entries:
        data = dict(entry["data"])
        data.pop("duration_ms", None)
        entries.append(
            {
                "turn": entry["turn"],
                "event_type": entry["event_type"],
                "data": data,
            }
        )
    return {
        "article": output.article,
        "brief": output.brief.model_dump(mode="json"),
        "summary": summary,
        "entries": entries,
    }


def test_public_config_and_artifact_schemas_match_legacy() -> None:
    config = ReportConfig(
        time_range=TimeRange.range(7, 8),
        focus_hints=["playoff race"],
        tone=ToneControls(snark_level=2, hype_level=3, seriousness=1),
    ).with_bias(favored=["Team Taco"], intensity=2)

    assert config.model_dump(mode="json") == LegacyReportConfig.model_validate(
        config.model_dump(mode="json")
    ).model_dump(mode="json")
    assert ReportConfig.model_json_schema() == LegacyReportConfig.model_json_schema()
    assert ReportBrief.model_json_schema() == LegacyReportBrief.model_json_schema()
    assert Article.model_json_schema() == LegacyArticle.model_json_schema()
    assert ArticleOutput.model_json_schema() == LegacyArticleOutput.model_json_schema()


def test_prompts_and_non_data_tool_contracts_match_legacy() -> None:
    config = ReportConfig.for_week(
        8,
        voice="deadpan beat writer",
        snark_level=2,
        focus_hints=["bench disasters"],
        custom_instructions="End with one clean callback.",
    )

    assert copied_system_prompt() == legacy_system_prompt()
    assert copied_user_message(config) == legacy_user_message(
        LegacyReportConfig.model_validate(config.model_dump(mode="json"))
    )
    assert COPIED_BRIEF_TOOLS == LEGACY_BRIEF_TOOLS
    assert COPIED_ARTICLE_TOOLS == LEGACY_ARTICLE_TOOLS
    assert COPIED_PROCEDURE_TOOLS == LEGACY_PROCEDURE_TOOLS
    assert COPIED_PERSISTENT_TOOLS == LEGACY_PERSISTENT_TOOLS


def test_prompt_and_procedure_assets_match_legacy() -> None:
    legacy = ROOT / "reporter_v2"
    copied = ROOT / "backend" / "services" / "reporter"

    for relative_path in (
        "prompts/system.md",
        "procedures/drafting.md",
        "procedures/research.md",
        "procedures/storyline.md",
        "procedures/verification.md",
    ):
        assert (copied / relative_path).read_bytes() == (
            legacy / relative_path
        ).read_bytes()


def test_generator_and_runner_output_match_legacy() -> None:
    data = DualLeagueData()
    copied = asyncio.run(
        copied_generate(
            data,  # type: ignore[arg-type]
            ReportConfig.for_week(8),
            complete=ScriptedCompletion(),
        )
    )
    legacy = asyncio.run(
        legacy_generate(
            data,  # type: ignore[arg-type]
            LegacyReportConfig.for_week(8),
            complete=ScriptedCompletion(),
        )
    )

    assert _stable_output(copied) == _stable_output(legacy)
