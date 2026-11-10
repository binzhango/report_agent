"""Stage an image and produce a graphics command."""

from report_agent.metadata.models import InputDefinition
from report_agent.models.inputs import ContentInput, ImageInput
from report_agent.models.results import RenderedContent
from report_agent.models.template import RenderContext
from report_agent.rendering.assets import graphics_content, stage_asset


class ImageRenderer:
    def render(
        self,
        value: ContentInput,
        definition: InputDefinition,
        context: RenderContext,
    ) -> RenderedContent:
        """Stage an image and produce a graphics command."""
        if not isinstance(value, ImageInput) or definition.type != "image":
            raise ValueError(
                "ImageRenderer requires ImageInput and an image declaration."
            )
        return graphics_content(
            stage_asset(value.path, context), context, definition.width
        )
