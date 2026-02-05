"""Agent components for the reporter.

Main entry points:
- ReporterAgent: Main agent for generating articles
- ReportConfig: Configuration for article generation
- generate_report: Convenience function for generating articles
"""

from agent.config import ReportConfig, TimeRange, ToneControls, BiasProfile
from agent.schemas import (
    ArticleOutput,
    ReportBrief,
    Fact,
    Storyline,
    Section,
)
from agent.research_log import ResearchLog, ResearchLogEntry
from agent.reporter_agent import ReporterAgent, ResearchAgent, DraftAgent
from agent.clarify import ClarificationAgent
from agent.workflows import (
    generate_report,
    generate_report_async,
    generate_with_config,
    generate_with_config_async,
    weekly_recap,
    weekly_recap_async,
    snarky_recap,
    snarky_recap_async,
)

__all__ = [
    # Config
    "ReportConfig",
    "TimeRange",
    "ToneControls",
    "BiasProfile",
    # Output schemas
    "ArticleOutput",
    "ReportBrief",
    "Fact",
    "Storyline",
    "Section",
    # Research log
    "ResearchLog",
    "ResearchLogEntry",
    # Agents
    "ReporterAgent",
    "ResearchAgent",
    "DraftAgent",
    "ClarificationAgent",
    # Workflow functions
    "generate_report",
    "generate_report_async",
    "generate_with_config",
    "generate_with_config_async",
    "weekly_recap",
    "weekly_recap_async",
    "snarky_recap",
    "snarky_recap_async",
]
