"""Ensure all supported content adapters participate in an actual TeX build."""

import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

from report_agent import RenderRequest, create_renderer


@pytest.mark.skipif(
    not shutil.which("texres") or not shutil.which("pdftotext"),
    reason="Requires texres and pdftotext",
)
def test_comprehensive_report_contains_charts_tables_and_repeated_headers(
    tmp_path: Path,
) -> None:
    bundle = Path(__file__).resolve().parents[2] / "examples/comprehensive"
    example = runpy.run_path(str(bundle / "render.py"))
    inputs = example["build_inputs"](tmp_path / "assets")
    result = create_renderer().render(
        RenderRequest(
            bundle, bundle / "template.json", inputs, tmp_path / "comprehensive.pdf"
        )
    )
    assert result.pdf_path is not None, result.diagnostics
    assert not result.diagnostics, result.diagnostics
    text = subprocess.check_output(["pdftotext", str(result.pdf_path), "-"], text=True)
    for expected in [
        "Momentum with discipline",
        "$1.69m",
        "Direct",
        "R&D Services",
        "Café Insights",
        "C-064",
        "stable pricing",
    ]:
        assert expected in text
    pages = [page for page in text.split("\f") if page.strip()]
    assert len(pages) == 7
    assert "Cohort" in pages[-2] and "Cohort" in pages[-1]
    graphics = [path for path in result.artifacts if path.suffix in {".pdf", ".png"}]
    assert len(graphics) == 3
    assert all(path.is_file() for path in result.artifacts)
