"""One render invocation, separate from reusable template metadata."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from report_agent.metadata.loader import MetadataSource
from report_agent.models.inputs import ContentInput
from report_agent.resolution.models import QuerySource


@dataclass(frozen=True)
class RenderRequest:
    template: Path
    metadata: MetadataSource
    inputs: Mapping[str, ContentInput]
    output: Path
    queries: Mapping[str, QuerySource] = field(default_factory=dict)
