"""Public Python API for template-based PDF reports.

Render text, images, graph files, matplotlib figures, and DataFrames into PDFs.
"""

from report_agent.application.bootstrap import create_renderer
from report_agent.application.request import RenderRequest
from report_agent.application.service import ReportRenderer
from report_agent.models.inputs import (
    FigureInput,
    GraphInput,
    ImageInput,
    TableInput,
    TextInput,
)
from report_agent.models.results import RenderResult

__all__ = [
    "FigureInput",
    "GraphInput",
    "ImageInput",
    "RenderRequest",
    "RenderResult",
    "ReportRenderer",
    "TableInput",
    "TextInput",
    "create_renderer",
]
