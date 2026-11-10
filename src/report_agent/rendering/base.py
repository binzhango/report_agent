"""Shared contract for content rendering strategies."""

from typing import Protocol

from report_agent.metadata.models import InputDefinition
from report_agent.models.inputs import ContentInput
from report_agent.models.results import RenderedContent
from report_agent.models.template import RenderContext


class ContentRenderer(Protocol):
    def render(
        self,
        value: ContentInput,
        definition: InputDefinition,
        context: RenderContext,
    ) -> RenderedContent: ...
