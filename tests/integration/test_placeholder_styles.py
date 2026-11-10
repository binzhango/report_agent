"""Compile all content types with the same metadata-driven presentation layer."""

import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest
from matplotlib.figure import Figure
from PIL import Image

from report_agent import (
    FigureInput,
    ImageInput,
    RenderRequest,
    TableInput,
    TextInput,
    create_renderer,
)


@pytest.mark.skipif(
    not shutil.which("texres") or not shutil.which("pdftotext"),
    reason="Requires texres and pdftotext",
)
def test_placeholder_styles_compile_for_text_image_graph_and_table(
    tmp_path: Path,
) -> None:
    bundle = Path(__file__).resolve().parents[2] / "examples/placeholder_styles"
    logo = tmp_path / "logo.png"
    Image.new("RGB", (20, 20), "teal").save(logo)
    figure = Figure(figsize=(4, 2))
    figure.subplots().plot([1, 2], [3, 4])
    result = create_renderer().render(
        RenderRequest(
            template=bundle,
            metadata=bundle / "template.json",
            inputs={
                "title": TextInput("Metadata styles"),
                "summary": TextInput("Revenue grew 12%."),
                "logo": ImageInput(logo),
                "trend": FigureInput(figure),
                "financial": TableInput(
                    pd.DataFrame({"Region": ["EMEA"], "Revenue": [1320.0]})
                ),
            },
            output=tmp_path / "styled.pdf",
        )
    )
    assert result.pdf_path is not None, result.diagnostics
    assert not result.diagnostics
    text = subprocess.check_output(["pdftotext", str(result.pdf_path), "-"], text=True)
    for expected in [
        "Executive summary",
        "Revenue grew 12%.",
        "Image placeholder",
        "Graph placeholder",
        "Table placeholder",
        "EMEA",
    ]:
        assert expected in text
    assert len([page for page in text.split("\f") if page.strip()]) == 3
    source = next(
        path for path in result.artifacts if path.name == "main.tex"
    ).read_text()
    assert source.count(r"\fcolorbox") == 3
    assert r"\color[HTML]{18343D}" in source


@pytest.mark.skipif(
    not shutil.which("texres") or not shutil.which("pdftotext"),
    reason="Requires texres and pdftotext",
)
def test_styled_flow_table_can_continue_across_pages(tmp_path: Path) -> None:
    template = tmp_path / "template"
    template.mkdir()
    (template / "main.tex").write_text(
        r"\documentclass{article}\usepackage{booktabs,multirow,longtable,xcolor}"
        r"\begin{document}<<records>>\par\end{document}"
    )
    metadata = {
        "id": "styled_longtable",
        "compiler": {"engine": "pdflatex"},
        "inputs": {
            "records": {
                "type": "table",
                "longtable": True,
                "show_index": False,
                "style": {
                    "typography": {"font_size_pt": 9, "color": "#18343D"},
                    "layout": {
                        "display": "block",
                        "heading": {"text": "Record detail"},
                    },
                },
            }
        },
    }
    result = create_renderer().render(
        RenderRequest(
            template,
            metadata,
            {
                "records": TableInput(
                    pd.DataFrame(
                        {
                            "Record": [f"R-{i:03}" for i in range(100)],
                            "Value": list(range(100)),
                        }
                    )
                )
            },
            tmp_path / "flow.pdf",
        )
    )
    assert result.pdf_path is not None, result.diagnostics
    assert not result.diagnostics
    text = subprocess.check_output(["pdftotext", str(result.pdf_path), "-"], text=True)
    pages = [page for page in text.split("\f") if page.strip()]
    assert len(pages) > 1
    assert all("Record" in page for page in pages)
    assert "R-000" in text and "R-099" in text


@pytest.mark.skipif(not shutil.which("texres"), reason="Requires texres")
def test_container_with_no_inner_width_fails_clearly(tmp_path: Path) -> None:
    template = tmp_path / "template"
    template.mkdir()
    (template / "main.tex").write_text(
        r"\documentclass{article}\usepackage{xcolor}"
        r"\begin{document}<<summary>>\par\end{document}"
    )
    result = create_renderer().render(
        RenderRequest(
            template,
            {
                "id": "narrow",
                "compiler": {"engine": "pdflatex"},
                "inputs": {
                    "summary": {
                        "type": "text",
                        "style": {
                            "layout": {"display": "block"},
                            "container": {"width": r"0.01\linewidth", "padding_pt": 10},
                        },
                    },
                },
            },
            {"summary": TextInput("Body")},
            tmp_path / "narrow.pdf",
        )
    )
    assert result.pdf_path is None
    assert "Container has no usable width" in result.diagnostics[0].message
