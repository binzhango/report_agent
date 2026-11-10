"""One graph strategy supporting graph files and caller-owned figures."""

from hashlib import sha256

from report_agent.metadata.models import InputDefinition
from report_agent.models.inputs import ContentInput, FigureInput, GraphInput
from report_agent.models.results import RenderedContent
from report_agent.models.template import RenderContext
from report_agent.rendering.assets import graphics_content, stage_asset
from report_agent.rendering.graphs.adapters import FigureExporter


class GraphRenderer:
    def __init__(self, figure_exporter: FigureExporter) -> None:
        self._figure_exporter = figure_exporter

    def render(
        self,
        value: ContentInput,
        definition: InputDefinition,
        context: RenderContext,
    ) -> RenderedContent:
        """Stage GraphInput files or export FigureInput objects to vector PDF."""
        if definition.type != "graph":
            raise ValueError("GraphRenderer requires a graph declaration.")
        if isinstance(value, GraphInput):
            source = value.path
        elif isinstance(value, FigureInput):
            name = sha256(context.input_name.encode()).hexdigest()[:16]
            source = self._figure_exporter.export(
                value.figure, context.workspace / "figure-exports" / f"{name}.pdf"
            )
        else:
            raise ValueError("GraphRenderer requires GraphInput or FigureInput.")
        return graphics_content(stage_asset(source, context), context, definition.width)
