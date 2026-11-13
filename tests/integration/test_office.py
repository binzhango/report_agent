"""Real conversions: semantic Office content and retained animation bytes."""

import importlib.util
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pytest
from PIL import Image

from report_agent import (
    AnimationInput,
    RenderRequest,
    TableInput,
    TextInput,
    create_renderer,
)
from report_agent.metadata.loader import MetadataLoader
from report_agent.resolution.animations import AnimationGenerators
from report_agent.resolution.models import QuerySource
from report_agent.resolution.resolver import ContentResolver
from report_agent.templates.odf import parse

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    shutil.which("soffice") is None, reason="LibreOffice is unavailable"
)


def test_docx_native_content_and_concurrent_profiles(tmp_path):
    def build(index):
        return create_renderer().render(
            RenderRequest(
                ROOT / "examples/office_docx",
                ROOT / "examples/office_docx/template.yaml",
                {
                    "title": TextInput(f"Review {index} & sales"),
                    "summary": TextInput("First paragraph.\n\nSecond paragraph."),
                    "sales": TableInput(
                        pd.DataFrame({"Region": ["EMEA", "APAC"], "Revenue": [12, 25]})
                    ),
                },
                tmp_path / f"review-{index}.docx",
            )
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(build, range(2)))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    for i, result in enumerate(results):
        assert result.output_path, result.diagnostics
        with ZipFile(result.output_path) as archive:
            root = parse(archive.read("word/document.xml"))
            assert f"Review {i} & sales" in "".join(root.itertext())
            assert len(root.findall(".//w:tr", ns)) == 3
        assert all(p.is_file() for p in result.artifacts)


def test_xlsx_types_formula_and_cached_value(tmp_path):
    result = create_renderer().render(
        RenderRequest(
            ROOT / "examples/office_xlsx",
            ROOT / "examples/office_xlsx/template.yaml",
            {
                "sales": TableInput(
                    pd.DataFrame(
                        {
                            "Region": ["=SUM(1,2)", "APAC", "AMER"],
                            "Revenue": [12, 25, 31],
                        }
                    )
                )
            },
            tmp_path / "sales.xlsx",
        )
    )
    assert result.output_path, result.diagnostics
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(result.output_path) as archive:
        sheets = [
            parse(archive.read(n))
            for n in archive.namelist()
            if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
        ]
        formulas = [
            cell
            for sheet in sheets
            for cell in sheet.findall(".//s:c", ns)
            if cell.find("s:f", ns) is not None
        ]
        assert len(formulas) == 1
        assert float(formulas[0].find("s:v", ns).text) == 68
        assert "=SUM(1,2)" in archive.read("xl/sharedStrings.xml").decode()


def test_query_to_animation_embedded_in_portable_deck(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "animation_example", ROOT / "examples/office_pptx/render.py"
    )
    example = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(example)
    metadata = MetadataLoader().load(ROOT / "examples/office_pptx/template.yaml")

    class CountingSource(example.DemoDataSource):
        calls = 0

        def fetch(self, source):
            self.calls += 1
            return super().fetch(source)

    source = CountingSource()
    media = tmp_path / "media"
    resolved = ContentResolver(
        sources={"demo": source},
        animation_generators=AnimationGenerators(
            {"sales_over_time": example.sales_over_time}
        ),
    ).resolve(
        metadata,
        queries={
            "sales_data": QuerySource(connection="demo", query="fixture", row_limit=100)
        },
        media_workspace=media,
    )
    assert not resolved.diagnostics, resolved.diagnostics
    assert source.calls == 1
    asset = resolved.inputs["sales_animation"]
    assert isinstance(asset, AnimationInput)
    data = asset.path.read_bytes()
    with Image.open(asset.path) as image:
        assert image.n_frames == 12
    result = create_renderer().render(
        RenderRequest(
            ROOT / "examples/office_pptx",
            metadata,
            resolved.inputs,
            tmp_path / "animated.pptx",
        )
    )
    assert result.output_path, result.diagnostics
    portable = tmp_path / "portable"
    portable.mkdir()
    shutil.copy(result.output_path, portable / "deck.pptx")
    shutil.rmtree(media)
    with ZipFile(portable / "deck.pptx") as archive:
        assert any(
            archive.read(n) == data
            for n in archive.namelist()
            if n.startswith("ppt/media/")
        )
        assert any(n.startswith("ppt/slides/_rels/") for n in archive.namelist())


def test_docx_figure_is_embedded_and_dimensions_preserved(tmp_path):
    from matplotlib.figure import Figure

    from report_agent import FigureInput

    folder = tmp_path / "template"
    folder.mkdir()
    text = (ROOT / "examples/office_docx/main.fodt").read_text()
    text = text.replace(
        "<office:text>",
        '<office:text><text:p><ra:image name="trend" '
        'width="10cm" height="5cm"/></text:p>',
    )
    (folder / "main.fodt").write_text(text)
    meta = (
        MetadataLoader().load(ROOT / "examples/office_docx/template.yaml").model_dump()
    )
    meta["inputs"]["trend"] = {"type": "graph"}
    figure = Figure(figsize=(6, 3))
    axis = figure.subplots()
    axis.plot([1, 2], [3, 7])
    size = tuple(figure.get_size_inches())
    position = axis.get_position().bounds
    result = create_renderer().render(
        RenderRequest(
            folder,
            meta,
            {
                "title": TextInput("Figure"),
                "summary": TextInput("Summary"),
                "sales": TableInput(pd.DataFrame({"Value": [1]})),
                "trend": FigureInput(figure),
            },
            tmp_path / "figure.docx",
        )
    )
    assert result.output_path, result.diagnostics
    with ZipFile(result.output_path) as archive:
        assert any(n.startswith("word/media/") for n in archive.namelist())
    assert tuple(figure.get_size_inches()) == size
    assert axis.get_position().bounds == position
