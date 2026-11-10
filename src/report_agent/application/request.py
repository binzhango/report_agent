"""One render invocation, separate from reusable template metadata."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from report_agent.metadata.loader import MetadataSource
from report_agent.models.inputs import ContentInput


@dataclass(frozen=True)
class RenderRequest:
    template: Path
    metadata: MetadataSource
    inputs: Mapping[str, ContentInput]
    output: Path
