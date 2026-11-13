"""Document backend interface at the application boundary."""

from typing import Protocol

from report_agent.application.request import RenderRequest
from report_agent.models.results import RenderResult


class DocumentBackend(Protocol):
    def render(self, request: RenderRequest, metadata) -> RenderResult: ...
