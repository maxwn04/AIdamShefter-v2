"""AI Fantasy Football Reporter Agent."""

from reporter.agent.config import ReportConfig
from reporter.agent.schemas import ArticleOutput, ReportBrief

__all__ = [
    "generate_report",
    "generate_report_async",
    "ReportConfig",
    "ReportBrief",
    "ArticleOutput",
]


def __getattr__(name: str):
    if name in {"generate_report", "generate_report_async"}:
        from reporter.agent import workflows

        return getattr(workflows, name)
    raise AttributeError(f"module 'reporter' has no attribute {name!r}")
