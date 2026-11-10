"""Results exchanged by rendering services."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class Diagnostic:
    stage: str
    code: str
    message: str
    severity: Literal["error", "warning"] = "error"
    input_name: str | None = None


@dataclass(frozen=True)
class RenderedContent:
    """Trusted renderer output; never accept this as caller-provided text."""

    latex: str
    assets: tuple[Path, ...] = ()
    required_packages: frozenset[str] = frozenset()
    kind: str | None = None


@dataclass(frozen=True)
class CompileResult:
    pdf_path: Path | None
    diagnostics: tuple[Diagnostic, ...] = ()
    log_path: Path | None = None


@dataclass(frozen=True)
class RenderResult:
    """References must point to retained artifacts, outside temporary workspaces."""

    pdf_path: Path | None
    diagnostics: tuple[Diagnostic, ...] = ()
    artifacts: tuple[Path, ...] = ()
