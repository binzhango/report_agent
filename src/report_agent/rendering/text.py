"""Escape plain text and enforce text limits."""

from report_agent.metadata.models import InputDefinition
from report_agent.models.inputs import ContentInput, TextInput
from report_agent.models.results import RenderedContent
from report_agent.models.template import RenderContext
from report_agent.rendering.latex import escape_text
from report_agent.validation.text import text_issues


class TextRenderer:
    def render(
        self,
        value: ContentInput,
        definition: InputDefinition,
        context: RenderContext,
    ) -> RenderedContent:
        """Escape plain text and enforce text limits."""
        if not isinstance(value, TextInput) or definition.type != "text":
            raise ValueError("TextRenderer requires a text declaration and TextInput.")
        issues = text_issues(value, definition)
        if issues:
            raise ValueError(issues[0][1])
        return RenderedContent(latex=escape_text(value.text))
