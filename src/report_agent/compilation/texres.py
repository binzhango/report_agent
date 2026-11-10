"""texres process adapter with per-build output/cache and bounded execution."""

import os
import signal
import subprocess
from math import isfinite
from pathlib import Path
from tempfile import mkdtemp

from report_agent.compilation.diagnostics import compile_warnings
from report_agent.metadata.models import CompilerOptions
from report_agent.models.results import CompileResult, Diagnostic


class TexresCompiler:
    def __init__(
        self, executable: str = "texres", timeout_seconds: float = 120
    ) -> None:
        if not isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("Compiler timeout must be positive.")
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def compile(self, entrypoint: Path, options: CompilerOptions) -> CompileResult:
        """Compile in the job workspace and normalize process diagnostics."""
        entrypoint = entrypoint.resolve()
        build = Path(mkdtemp(prefix=".report-compile-", dir=entrypoint.parent))
        engine = {
            "pdflatex": "-pdf",
            "xelatex": "-xelatex",
            "lualatex": "-lualatex",
        }[options.engine]
        command = [
            self.executable,
            engine,
            "--cache-directory",
            str(build / "cache"),
            "-output-directory",
            str(build),
            "--keep-logs",
            "-halt-on-error",
            "-latexoption=-no-shell-escape",
            str(entrypoint),
        ]
        transcript = build / "process.log"
        log = build / f"{entrypoint.stem}.log"

        def failure(code: str, message: str) -> CompileResult:
            if not transcript.is_file():
                transcript.write_text(message, encoding="utf-8")
            return CompileResult(
                None,
                (Diagnostic("compilation", code, message),),
                log if log.is_file() else transcript,
            )

        try:
            process = subprocess.Popen(
                command,
                cwd=entrypoint.parent,
                env={**os.environ, "TEX_RS_CACHE_DIR": str(build / "cache")},
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=os.name == "posix",
            )
        except FileNotFoundError:
            return failure(
                "compiler_not_found", f"Compiler not found: {self.executable}"
            )
        try:
            output, _ = process.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            self._kill(process)
            output, _ = process.communicate()
            transcript.write_text(output, encoding="utf-8")
            return failure(
                "compiler_timeout",
                f"Compilation exceeded {self.timeout_seconds} seconds.",
            )
        except BaseException:
            self._kill(process)
            process.communicate()
            raise
        transcript.write_text(output, encoding="utf-8")
        details = (
            log.read_text(encoding="utf-8", errors="replace")
            if log.is_file()
            else output
        )
        if process.returncode != 0:
            return failure(
                "compiler_failed",
                details[-4000:] or f"Compiler exited with {process.returncode}.",
            )
        pdf = build / f"{entrypoint.stem}.pdf"
        if not pdf.is_file() or pdf.stat().st_size == 0:
            return failure("missing_pdf", "Compiler completed without producing a PDF.")
        with pdf.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                return failure("invalid_pdf", "Compiler output is not a PDF.")
        warnings = compile_warnings(details, entrypoint.read_text(encoding="utf-8"))
        return CompileResult(pdf, warnings, log if log.is_file() else transcript)

    @staticmethod
    def _kill(process: subprocess.Popen) -> None:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.poll() is None:
            process.kill()
