"""Default dependency composition, shared by Python, CLI, and future HTTP."""

from report_agent.application.service import ReportRenderer
from report_agent.application.validation import RenderValidator
from report_agent.compilation.texres import TexresCompiler
from report_agent.metadata.loader import MetadataLoader
from report_agent.presentation.styler import LatexPlaceholderStyler
from report_agent.rendering.graphs.adapters import MatplotlibFigureExporter
from report_agent.rendering.graphs.renderer import GraphRenderer
from report_agent.rendering.images import ImageRenderer
from report_agent.rendering.registry import RendererRegistry
from report_agent.rendering.tables import StylerTableRenderer
from report_agent.rendering.text import TextRenderer
from report_agent.storage.artifacts import LocalArtifactStore
from report_agent.storage.workspace import TemporaryWorkspaceManager
from report_agent.templates.engine import JinjaTemplateEngine
from report_agent.templates.repository import LocalTemplateRepository


def create_renderer() -> ReportRenderer:
    """Assemble the default template, content, compiler, and storage services."""
    template_engine = JinjaTemplateEngine()
    return ReportRenderer(
        metadata_loader=MetadataLoader(),
        templates=LocalTemplateRepository(),
        validator=RenderValidator(template_engine),
        renderers=RendererRegistry(
            {
                "text": TextRenderer(),
                "image": ImageRenderer(),
                "graph": GraphRenderer(MatplotlibFigureExporter()),
                "table": StylerTableRenderer(),
            }
        ),
        template_engine=template_engine,
        compiler=TexresCompiler(),
        workspaces=TemporaryWorkspaceManager(),
        artifacts=LocalArtifactStore(),
        styler=LatexPlaceholderStyler(),
    )
