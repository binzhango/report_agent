"""Process failures must not become successful or stale report results."""

import os
import sys
from pathlib import Path

import pytest

from report_agent.compilation.texres import TexresCompiler
from report_agent.metadata.models import CompilerOptions


def test_missing_compiler_is_reported(tmp_path: Path) -> None:
    result = TexresCompiler(str(tmp_path / "missing")).compile(
        tmp_path / "main.tex", CompilerOptions()
    )
    assert result.pdf_path is None
    assert result.diagnostics[0].code == "compiler_not_found"


@pytest.mark.skipif(
    os.name != "posix", reason="Executable script fixture uses a shebang"
)
@pytest.mark.parametrize(
    "body, timeout, code",
    [
        ("import time; time.sleep(30)", 0.05, "compiler_timeout"),
        ("pass", 5, "missing_pdf"),
        ("raise SystemExit(1)", 5, "compiler_failed"),
    ],
)
def test_process_failures(tmp_path: Path, body: str, timeout: float, code: str) -> None:
    executable = tmp_path / "compiler"
    executable.write_text(f"#!{sys.executable}\n{body}\n")
    executable.chmod(0o755)
    (tmp_path / "main.pdf").write_bytes(b"%PDF-stale")
    result = TexresCompiler(str(executable), timeout).compile(
        tmp_path / "main.tex", CompilerOptions()
    )
    assert result.pdf_path is None
    assert result.diagnostics[0].code == code
