"""Office contracts tested without an installed office application."""

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
from report_agent.backends.libreoffice import LibreOfficeBackend, verify_package
from report_agent.compilation.libreoffice import ConversionError, LibreOfficeConverter
from report_agent.metadata.loader import MetadataLoader
from report_agent.metadata.office import ExportOptions
from report_agent.models.results import RenderResult
from report_agent.templates.odf import NS, OdfTemplate, parse

ROOT = Path(__file__).resolve().parents[2]


def metadata(fmt="docx"):
    return MetadataLoader().load(ROOT / f"examples/office_{fmt}/template.yaml")


def test_result_legacy_and_generic_paths():
    assert RenderResult(Path("a.pdf")).output_path == Path("a.pdf")
    assert RenderResult(output_path=Path("a.pdf")).pdf_path == Path("a.pdf")
    assert RenderResult(output_path=Path("a.xlsx")).pdf_path is None
    with pytest.raises(ValueError):
        RenderResult(Path("a.pdf"), output_path=Path("b.pdf"))


def test_strict_schema_rejects_latex_options():
    value = metadata().model_dump()
    value["inputs"]["title"]["width"] = "0.9\\linewidth"
    with pytest.raises(ValueError):
        MetadataLoader().load(value)
    value = metadata().model_dump()
    value["document"]["format"] = "pptx"
    with pytest.raises(ValueError):
        MetadataLoader().load(value)


def test_xml_escaping_paragraphs_and_table_coverage(tmp_path):
    meta = metadata()
    template = OdfTemplate(
        (ROOT / "examples/office_docx/main.fodt").read_text(), "docx"
    )
    result = template.expand(
        {
            "title": TextInput('<Title & "value">'),
            "summary": TextInput("First  paragraph\nline\n\nSecond"),
            "sales": TableInput(pd.DataFrame({"Data": ["<ra:text/>", "=SUM(1,2)"]})),
        },
        meta.inputs,
        tmp_path,
    )
    root = parse(result)
    text = "".join(root.itertext())
    assert '<Title&"value">' in text
    assert root.findall(".//text:s", NS)
    assert "<ra:text/>" in text
    assert "=SUM(1,2)" in text
    assert root.findall(".//text:line-break", NS)
    assert len(root.findall(".//table:table-row", NS)) == 3
    assert not root.findall(".//ra:text", NS)


def test_xml_dtd_and_external_asset_rejected():
    with pytest.raises(Exception):
        parse('<!DOCTYPE a [<!ENTITY x "bad">]><a>&x;</a>')
    source = (
        (ROOT / "examples/office_docx/main.fodt")
        .read_text()
        .replace(
            "<office:body>",
            '<office:body><draw:image xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="file:///etc/passwd"/>',
        )
    )
    with pytest.raises(ValueError, match="External"):
        OdfTemplate(source, "docx")


def test_office_preflight_prevents_conversion(tmp_path):
    class Never:
        def convert(self, *args):
            raise AssertionError("Unexpected conversion")

    result = create_renderer(
        office_backend=LibreOfficeBackend(converter=Never())
    ).render(
        RenderRequest(
            ROOT / "examples/office_docx", metadata(), {}, tmp_path / "a.docx"
        )
    )
    assert result.output_path is None
    assert {d.code for d in result.diagnostics} == {"missing_input"}


def test_failure_preserves_output_and_source(tmp_path):
    class Fail:
        def convert(self, *args):
            raise ConversionError("converter_failed", "intentional")

    output = tmp_path / "report.docx"
    output.write_bytes(b"previous")
    result = create_renderer(
        office_backend=LibreOfficeBackend(converter=Fail())
    ).render(
        RenderRequest(
            ROOT / "examples/office_docx",
            metadata(),
            {
                "title": TextInput("title"),
                "summary": TextInput("summary"),
                "sales": TableInput(pd.DataFrame({"value": [1]})),
            },
            output,
        )
    )
    assert result.output_path is None
    assert result.diagnostics[0].code == "converter_failed"
    assert output.read_bytes() == b"previous"
    assert any(p.name == "expanded.fodt" for p in result.artifacts)


def test_package_missing_parts_and_flattened_media(tmp_path):
    invalid = tmp_path / "invalid.pptx"
    with ZipFile(invalid, "w") as z:
        z.writestr("foo", "bar")
    with pytest.raises(ConversionError):
        verify_package(invalid, "pptx")
    gif = tmp_path / "static.gif"
    Image.new("RGB", (10, 10)).save(gif)
    poster = tmp_path / "poster.png"
    Image.new("RGB", (10, 10)).save(poster)
    template = OdfTemplate(
        (ROOT / "examples/office_pptx/main.fodp").read_text(), "pptx"
    )
    with pytest.raises(ValueError, match="flattened"):
        template.expand(
            {"sales_animation": AnimationInput(gif, poster)},
            metadata("pptx").inputs,
            tmp_path,
        )


def test_output_collision_rejected(tmp_path):
    meta = metadata()
    root = tmp_path / "template"
    root.mkdir()
    source = root / "main.fodt"
    source.write_text((ROOT / "examples/office_docx/main.fodt").read_text())
    protected = root / "source.docx"
    protected.write_bytes(b"original")
    result = create_renderer().render(RenderRequest(root, meta, {}, protected))
    assert result.output_path is None
    assert protected.read_bytes() == b"original"
    assert "overwrite" in result.diagnostics[0].message


def test_limits():
    for invalid in (
        {"fps": 31},
        {"duration_seconds": 31},
        {"format": "mp4", "width_px": 101},
    ):
        with pytest.raises(ValueError):
            ExportOptions(**invalid)
    with pytest.raises(ValueError):
        LibreOfficeConverter(timeout_seconds=0)


def test_calc_literals_types_and_precision(tmp_path):
    template = OdfTemplate(
        (ROOT / "examples/office_xlsx/main.fods").read_text(), "xlsx"
    )
    result = template.expand(
        {"sales": TableInput(pd.DataFrame({"v": ["=SUM(1,2)", True, 12]}))},
        metadata("xlsx").inputs,
        tmp_path,
    )
    root = parse(result)
    cells = root.findall(".//table:table-cell", NS)
    assert cells[1].get("{" + NS["office"] + "}value-type") == "string"
    assert cells[1].get("{" + NS["table"] + "}formula") is None
    assert "xmlns:of=" in result
    template = OdfTemplate(
        (ROOT / "examples/office_xlsx/main.fods").read_text(), "xlsx"
    )
    with pytest.raises(ValueError, match="Large integer"):
        template.expand(
            {"sales": TableInput(pd.DataFrame({"id": [1234567890123456]}))},
            metadata("xlsx").inputs,
            tmp_path,
        )


def test_converter_missing_and_timeout_are_bounded(tmp_path):
    import sys

    source = tmp_path / "input.fodt"
    source.write_text("<document/>")
    with pytest.raises(ConversionError) as missing:
        LibreOfficeConverter(executable=str(tmp_path / "missing")).convert(
            source, "docx", tmp_path / "missing-export"
        )
    assert missing.value.code == "converter_not_found"
    executable = tmp_path / "fake-office"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import sys,time\n"
        "if '--version' in sys.argv:\n print('Test Office')\n"
        "else:\n time.sleep(10)\n"
    )
    executable.chmod(0o755)
    with pytest.raises(ConversionError) as timeout:
        LibreOfficeConverter(executable=str(executable), timeout_seconds=0.2).convert(
            source, "docx", tmp_path / "timeout-export"
        )
    assert timeout.value.code == "converter_timeout"
    assert (tmp_path / "timeout-export/conversion.log").exists()


def test_animation_generator_timeout_and_unknown_id(tmp_path):
    import time

    from report_agent.resolution.animations import AnimationGenerators

    def slow(tables, options):
        time.sleep(10)

    registry = AnimationGenerators({"slow": slow}, timeout_seconds=0.1)
    with pytest.raises(ValueError, match="Unknown"):
        registry.generate("unknown", {}, ExportOptions(), tmp_path / "unknown")
    with pytest.raises(ValueError, match="timed out"):
        registry.generate("slow", {}, ExportOptions(), tmp_path / "slow")
