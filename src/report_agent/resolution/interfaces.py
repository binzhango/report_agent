"""Adapters must enforce SQL policy; this package provides no SQL/LLM client."""

from collections.abc import Mapping
from typing import Protocol

from pandas import DataFrame

from report_agent.resolution.models import QuerySource, TableSummary


class DataSource(Protocol):
    def fetch(self, source: QuerySource) -> DataFrame:
        """Validate read-only SQL/access policy, bind params, and enforce limits.

        Implementations must also use read-only credentials/transactions and
        timeouts. A SELECT-looking string alone is not a security boundary.
        """
        ...


class AgentTextGenerator(Protocol):
    def generate(self, prompt: str, tables: Mapping[str, TableSummary]) -> str:
        """Produce plain text using only the supplied, untrusted table summaries."""
        ...
