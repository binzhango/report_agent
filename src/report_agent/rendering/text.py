"""Escape plain text and enforce text limits."""

from report_agent.metadata.models import InputDefinition
from report_agent.models.inputs import ContentInput, TextInput
from report_agent.models.results import RenderedContent
from report_agent.models.template import RenderContext
from report_agent.rendering.latex import escape_text


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
        if not isinstance(value.text, str):
            raise ValueError("TextInput.text must be a string.")
        if definition.max_chars is not None and len(value.text) > definition.max_chars:
            raise ValueError(
                f"Text exceeds the {definition.max_chars}-character limit."
            )
        return RenderedContent(latex=escape_text(value.text))
