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

    pdf_path: Path | None = None
    diagnostics: tuple[Diagnostic, ...] = ()
    artifacts: tuple[Path, ...] = ()
    output_path: Path | None = None
    output_format: str | None = None

    def __post_init__(self):
        path = self.output_path or self.pdf_path
        if self.pdf_path and self.output_path and self.pdf_path != self.output_path:
            raise ValueError("Conflicting result paths.")
        if path:
            fmt = path.suffix.lstrip(".").lower()
            if self.output_format and self.output_format != fmt:
                raise ValueError("Conflicting output format.")
            if self.pdf_path and fmt != "pdf":
                raise ValueError("pdf_path must identify PDF output.")
            object.__setattr__(self, "output_path", path)
            object.__setattr__(self, "output_format", fmt)
            if fmt == "pdf":
                object.__setattr__(self, "pdf_path", path)
