"""Public Python API for template-based PDF and Office reports.

Render text, images, figures, tables, and encoded animations into reports.
"""

from report_agent.application.bootstrap import create_renderer
from report_agent.application.request import RenderRequest
from report_agent.application.service import ReportRenderer
from report_agent.models.inputs import (
    AnimationInput,
    FigureInput,
    GraphInput,
    ImageInput,
    TableInput,
    TextInput,
)
from report_agent.models.results import RenderResult

__all__ = [
    "AnimationInput",
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
