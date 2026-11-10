"""Template resources and per-render context."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TemplateBundle:
    root: Path
    entrypoint: Path
    resources: tuple[Path, ...] = ()


@dataclass(frozen=True)
class RenderContext:
    workspace: Path
    input_name: str
    document_root: Path | None = None
