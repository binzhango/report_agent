"""Optional upstream data/agent resolution; the renderer remains independent."""

from report_agent.resolution.interfaces import AgentTextGenerator, DataSource
from report_agent.resolution.models import QuerySource, ResolutionResult, TableSummary
from report_agent.resolution.resolver import ContentResolver

__all__ = [
    "AgentTextGenerator",
    "ContentResolver",
    "DataSource",
    "QuerySource",
    "ResolutionResult",
    "TableSummary",
]
