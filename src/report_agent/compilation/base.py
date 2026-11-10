"""Compiler abstraction independent of a particular executable."""

from pathlib import Path
from typing import Protocol

from report_agent.metadata.models import CompilerOptions
from report_agent.models.results import CompileResult


class LatexCompiler(Protocol):
    def compile(self, entrypoint: Path, options: CompilerOptions) -> CompileResult: ...
