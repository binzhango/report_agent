"""Real texres and CLI integration; skipped when executables are unavailable."""

import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from report_agent import RenderRequest, TextInput, create_renderer
from report_agent.interfaces.cli.app import app

pytestmark = pytest.mark.skipif(
    not shutil.which("texres") or not shutil.which("pdftotext"),
    reason="Requires texres and pdftotext",
)
BUNDLE = Path(__file__).resolve().parents[2] / "examples/plain_text"


@pytest.mark.parametrize("extension", ["json", "yaml"])
def test_real_pdf_contains_literal_text(tmp_path: Path, extension: str) -> None:
    result = create_renderer().render(
        RenderRequest(
            BUNDLE,
            BUNDLE / f"template.{extension}",
            {
                "title": TextInput("Sales & costs"),
                "summary": TextInput(r"12% $5 x_y \input{secret}"),
            },
            tmp_path / "report.pdf",
        )
    )
    assert result.pdf_path is not None, result.diagnostics
    text = subprocess.check_output(["pdftotext", str(result.pdf_path), "-"], text=True)
    assert "Sales & costs" in text
    assert r"12% $5 x_y \input{secret}" in text
    assert "Reporting period not specified" in text
    assert "Prepared for internal review." in text


def test_cli_render_and_validation_failure(tmp_path: Path) -> None:
    runner = CliRunner()
    arguments = [
        "render",
        str(BUNDLE),
        "--metadata",
        str(BUNDLE / "template.json"),
        "--output",
        str(tmp_path / "cli.pdf"),
    ]
    failed = runner.invoke(app, arguments)
    assert failed.exit_code == 1
    assert "missing_input" in failed.output
    success = runner.invoke(
        app,
        arguments + ["--text", "title=CLI example", "--text", "summary=Hello world"],
    )
    assert success.exit_code == 0, success.output
    assert (tmp_path / "cli.pdf").is_file()
