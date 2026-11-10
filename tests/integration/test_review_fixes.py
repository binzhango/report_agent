"""Exercise package validation, table-overflow policy, and CLI file inputs."""

import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest
from matplotlib.figure import Figure
from PIL import Image
from typer.testing import CliRunner

from report_agent import RenderRequest, TableInput, TextInput, create_renderer
from report_agent.interfaces.cli.app import app
from report_agent.metadata.models import TemplateMetadata
from report_agent.resolution import ContentResolver

pytestmark = pytest.mark.skipif(
    not shutil.which("texres") or not shutil.which("pdftotext"),
    reason="Requires texres and pdftotext",
)


def test_wide_table_fails_and_keeps_previous_pdf(tmp_path: Path) -> None:
    template = tmp_path / "template"
    template.mkdir()
    (template / "main.tex").write_text(
        r"\documentclass{article}\usepackage{booktabs}\begin{document}\begin{center}<<sales>>\end{center}\end{document}"
    )
    output = tmp_path / "report.pdf"
    output.write_bytes(b"previous report")
    frame = pd.DataFrame({f"Quarter_{index}": [index] for index in range(30)})
    result = create_renderer().render(
        RenderRequest(
            template,
            {
                "id": "wide",
                "compiler": {"engine": "pdflatex"},
                "inputs": {"sales": {"type": "table", "show_index": False}},
            },
            {"sales": TableInput(frame)},
            output,
        )
    )
    assert result.pdf_path is None, result.diagnostics
    assert any(
        issue.code == "table_overflow" and issue.input_name == "sales"
        for issue in result.diagnostics
    )
    assert output.read_bytes() == b"previous report"
    assert any(path.name == "compile.log" for path in result.artifacts)


def test_ot1_special_characters_remain_literal(tmp_path: Path) -> None:
    template = tmp_path / "template"
    template.mkdir()
    (template / "main.tex").write_text(
        r"\documentclass{article}\begin{document}<<summary>>\end{document}"
    )
    result = create_renderer().render(
        RenderRequest(
            template,
            {
                "id": "ot1",
                "compiler": {"engine": "pdflatex"},
                "inputs": {"summary": {"type": "text"}},
            },
            {"summary": TextInput("Less < greater > pipe |")},
            tmp_path / "ot1.pdf",
        )
    )
    assert result.pdf_path is not None, result.diagnostics
    text = subprocess.check_output(["pdftotext", str(result.pdf_path), "-"], text=True)
    assert "Less < greater > pipe |" in text


def test_generated_text_is_escaped_before_compilation(tmp_path: Path) -> None:
    class Generator:
        def generate(self, prompt, tables):
            assert tables["sales"].row_count == 1
            return r"Growth 12% & \input{not-a-file}"

    template = tmp_path / "template"
    template.mkdir()
    (template / "main.tex").write_text(
        r"\documentclass{article}\usepackage{booktabs}"
        r"\begin{document}<<summary>>\par<<sales>>\end{document}"
    )
    metadata = TemplateMetadata.model_validate(
        {
            "id": "generated",
            "compiler": {"engine": "pdflatex"},
            "inputs": {
                "sales": {"type": "table"},
                "summary": {
                    "type": "text",
                    "source": "agent",
                    "prompt": "Summarize sales",
                    "uses": ["sales"],
                },
            },
        }
    )
    resolved = ContentResolver(sources={}, text_generator=Generator()).resolve(
        metadata, inputs={"sales": TableInput(pd.DataFrame({"Revenue": [123]}))}
    )
    assert not resolved.diagnostics
    result = create_renderer().render(
        RenderRequest(template, metadata, resolved.inputs, tmp_path / "generated.pdf")
    )
    assert result.pdf_path is not None, result.diagnostics
    source = next(path for path in result.artifacts if path.name == "main.tex")
    assert r"\textbackslash{}input\{not-a-file\}" in source.read_text()
    text = subprocess.check_output(["pdftotext", str(result.pdf_path), "-"], text=True)
    assert r"Growth 12% & \input{not-a-file}" in text


def test_cli_manifest_and_file_flags_render_all_content(tmp_path: Path) -> None:
    template = tmp_path / "template"
    template.mkdir()
    (template / "main.tex").write_text(
        r"\documentclass{article}\usepackage{booktabs,graphicx}\begin{document}<<summary>>\par<<logo>>\par<<chart>>\par<<sales>>\end{document}"
    )
    metadata = template / "template.json"
    metadata.write_text(
        json.dumps(
            {
                "id": "cli_files",
                "compiler": {"engine": "pdflatex"},
                "inputs": {
                    "summary": {"type": "text"},
                    "logo": {"type": "image", "width": "10mm"},
                    "chart": {"type": "graph", "width": "60mm"},
                    "sales": {"type": "table", "show_index": False},
                },
            }
        )
    )
    Image.new("RGB", (20, 20), "teal").save(tmp_path / "logo.png")
    figure = Figure(figsize=(4, 2))
    figure.subplots().plot([1, 2], [3, 4])
    figure.savefig(tmp_path / "chart.pdf")
    (tmp_path / "sales.csv").write_text("Region,Revenue\nEMEA,1320\n")
    manifest = tmp_path / "inputs.yaml"
    manifest.write_text(
        "inputs:\n  summary: From manifest\n"
        "  logo: {type: image, path: logo.png}\n"
        "  chart: {type: graph, path: chart.pdf}\n"
        "  sales: {type: table, path: sales.csv}\n"
    )
    output = tmp_path / "cli.pdf"
    base = [
        "render",
        str(template),
        "--metadata",
        str(metadata),
        "--output",
        str(output),
    ]
    result = CliRunner().invoke(
        app, base + ["--inputs", str(manifest), "--text", "summary=Explicit override"]
    )
    assert result.exit_code == 0, result.output
    text = subprocess.check_output(["pdftotext", str(output), "-"], text=True)
    assert "Explicit override" in text and "EMEA" in text
    result = CliRunner().invoke(
        app,
        base
        + [
            "--text",
            "summary=Flags only",
            "--image",
            f"logo={tmp_path / 'logo.png'}",
            "--graph",
            f"chart={tmp_path / 'chart.pdf'}",
            "--table",
            f"sales={tmp_path / 'sales.csv'}",
        ],
    )
    assert result.exit_code == 0, result.output
