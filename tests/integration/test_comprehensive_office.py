"""Comprehensive samples prove page/slide/tab structure and cross-tab calculation."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
from PIL import Image

from report_agent.templates.odf import parse

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    shutil.which("soffice") is None, reason="LibreOffice unavailable"
)


@pytest.fixture(scope="module")
def comprehensive(tmp_path_factory):
    output = tmp_path_factory.mktemp("comprehensive-office")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples/office_comprehensive/render.py"),
            "--output-root",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env={
            **os.environ,
            "MPLCONFIGDIR": str(output / "mpl"),
            "XDG_CACHE_HOME": str(output / "cache"),
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return output


def test_docx_sections_tables_and_all_cohorts(comprehensive):
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with ZipFile(comprehensive / "comprehensive-document.docx") as z:
        root = parse(z.read("word/document.xml"))
        text = "".join(root.itertext())
        # Page-style selection must not export a leading forced break to Word.
        first = root.find("w:body/w:p", ns)
        key = "{" + ns["w"] + "}"
        direct_break = first.find("w:pPr/w:pageBreakBefore", ns)
        assert direct_break is None or direct_break.get(key + "val") in {
            "false",
            "0",
            "off",
        }
        style_id = first.find("w:pPr/w:pStyle", ns).get(key + "val")
        styles = parse(z.read("word/styles.xml"))
        seen = set()
        while style_id and style_id not in seen:
            seen.add(style_id)
            style = styles.find(f'w:style[@w:styleId="{style_id}"]', ns)
            assert style is not None
            inherited_break = style.find("w:pPr/w:pageBreakBefore", ns)
            assert inherited_break is None or inherited_break.get(key + "val") in {
                "false",
                "0",
                "off",
            }
            parent = style.find("w:basedOn", ns)
            style_id = parent.get(key + "val") if parent is not None else None
        assert first.find(".//w:drawing", ns) is not None
        assert all(f"C-{i:03}" in text for i in range(1, 65))
        assert len(root.findall(".//w:tbl", ns)) == 7
        sizes = root.findall(".//w:pgSz", ns)
        key = "{" + ns["w"] + "}"
        assert any(int(e.get(key + "w")) > int(e.get(key + "h")) for e in sizes)
        assert any(int(e.get(key + "w")) < int(e.get(key + "h")) for e in sizes)
        assert root.findall(".//w:tblHeader", ns)
        assert root.findall(".//w:shd", ns)


def test_pptx_explicit_slide_order_typography_and_animation(comprehensive):
    ns = {
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    }
    with ZipFile(comprehensive / "comprehensive-presentation.pptx") as z:
        root = parse(z.read("ppt/presentation.xml"))
        assert len(root.findall(".//p:sldId", ns)) == 9
        slide = parse(z.read("ppt/slides/slide3.xml"))
        assert "Every region grew from Q2" in "".join(slide.itertext())
        assert any(e.get("sz") == "3000" for e in slide.findall(".//a:rPr", ns))
        assert len(slide.findall(".//a:tr", ns)) == 6
        fills = [
            e.get("val").upper()
            for e in slide.findall(".//a:tcPr/a:solidFill/a:srgbClr", ns)
        ]
        assert "18343D" in fills and "F1F6F7" in fills and "FFFFFF" in fills
        media = [
            z.read(n)
            for n in z.namelist()
            if n.startswith("ppt/media/") and n.endswith(".gif")
        ]
        assert len(media) == 1
        from io import BytesIO

        with Image.open(BytesIO(media[0])) as image:
            assert image.n_frames == 36
            assert image.info["loop"] == 0


def test_xlsx_forward_formulas_numeric_types_and_tabs(comprehensive):
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(comprehensive / "comprehensive-workbook.xlsx") as z:
        root = parse(z.read("xl/workbook.xml"))
        assert [s.get("name") for s in root.findall(".//s:sheet", ns)] == [
            "Summary",
            "Regions",
            "Channels",
            "Service",
            "Products",
            "Cohorts",
            "Monthly",
        ]
        summary = parse(z.read("xl/worksheets/sheet1.xml"))
        values = {
            cell.get("r"): float(cell.find("s:v", ns).text)
            for cell in summary.findall(".//s:c", ns)
            if cell.find("s:f", ns) is not None
        }
        assert values["B3"] == 4770
        assert values["B4"] == 4130
        assert values["B5"] == pytest.approx((4770 / 4130 - 1) * 100)
        assert values["B6"] == 377
        assert values["B7"] == 4770
        assert values["B8"] == 64
        regions = parse(z.read("xl/worksheets/sheet2.xml"))
        assert regions.find('.//s:c[@r="C2"]', ns).get("t") == "n"
        styles = parse(z.read("xl/styles.xml"))
        assert styles.find("s:numFmts", ns) is not None
