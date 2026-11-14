"""Regressions for early validation, publication and converter lifecycle failures."""

import io
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pandas as pd
import pytest
from PIL import Image

from report_agent import RenderRequest, TableInput, TextInput, create_renderer
from report_agent.backends.libreoffice import LibreOfficeBackend, verify_package
from report_agent.compilation.libreoffice import ConversionError, LibreOfficeConverter
from report_agent.metadata.office import OfficeInputDefinition
from report_agent.storage.artifacts import LocalArtifactStore, publish_snapshot
from report_agent.templates.odf import OdfTemplate
from report_agent.validation.text import text_issues

ROOT = Path(__file__).resolve().parents[2]


def request(tmp_path, title="Review"):
    return RenderRequest(
        ROOT / "examples/office_docx",
        ROOT / "examples/office_docx/template.yaml",
        {
            "title": TextInput(title),
            "summary": TextInput("Summary"),
            "sales": TableInput(pd.DataFrame({"value": [1]})),
        },
        tmp_path / "review.docx",
    )


@pytest.mark.parametrize(
    "text", ["bad\ufffeX", "bad\uffffX", "bad\ud800X", "bad\udfffX", "bad\x00X"]
)
def test_office_invalid_characters_never_start_conversion(tmp_path, text):
    class Never:
        def convert(self, *args):
            raise AssertionError("Converter must not run")

    result = create_renderer(
        office_backend=LibreOfficeBackend(converter=Never())
    ).render(request(tmp_path, text))
    issue = result.diagnostics[0]
    assert (issue.stage, issue.code, issue.input_name) == (
        "input_validation",
        "invalid_text",
        "title",
    )
    assert result.output_path is None


def test_xml_char_production_accepts_legal_boundaries():
    value = TextInput("\t\n\r \ud7ff\ue000\ufffd\U00010000\U0010ffff")
    assert not text_issues(value, OfficeInputDefinition(type="text"))


class PackageConverter:
    fail = False

    def convert(self, source, fmt, directory):
        directory.mkdir()
        (directory / "conversion.log").write_text("failed" if self.fail else "success")
        if self.fail:
            raise ConversionError("converter_failed", "original conversion failure")
        (directory / "version.txt").write_text("Test Office")
        target = directory / "report.docx"
        with ZipFile(target, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("_rels/.rels", "<Relationships/>")
            archive.writestr("word/document.xml", "<document/>")
        return target


def test_repeated_builds_replace_assets_and_failed_run_logs(tmp_path):
    converter = PackageConverter()
    renderer = create_renderer(office_backend=LibreOfficeBackend(converter=converter))
    render_request = request(tmp_path)
    assert renderer.render(render_request).output_path
    previous = render_request.output.read_bytes()
    artifacts = tmp_path / "review.artifacts"
    stale = artifacts / "report-assets/stale-hash.png"
    stale.parent.mkdir()
    stale.write_bytes(b"old")
    converter.fail = True
    result = renderer.render(render_request)
    assert result.diagnostics[0].code == "converter_failed"
    assert not stale.exists() and not (artifacts / "build.json").exists()
    assert (artifacts / "export/conversion.log").read_text() == "failed"
    assert render_request.output.read_bytes() == previous
    (artifacts / "old-failure.log").write_text("stale failure")
    converter.fail = False
    result = renderer.render(render_request)
    assert result.output_path
    assert not (artifacts / "old-failure.log").exists()
    assert (artifacts / "export/conversion.log").read_text() == "success"
    assert (
        json.loads((artifacts / "build.json").read_text())["version"] == "Test Office"
    )
    assert set(p for p in artifacts.rglob("*") if p.is_file()) == set(result.artifacts)


def test_failed_retention_does_not_mask_conversion_error(tmp_path):
    class BrokenStore:
        def publish(self, *args):
            raise OSError("retention failed")

    converter = PackageConverter()
    converter.fail = True
    result = create_renderer(
        office_backend=LibreOfficeBackend(
            converter=converter,
            artifacts=BrokenStore(),
        )
    ).render(request(tmp_path))
    assert result.diagnostics[0].code == "converter_failed"
    assert result.diagnostics[0].message == "original conversion failure"
    assert result.diagnostics[1].code == "artifact_retention_failed"
    assert result.diagnostics[1].severity == "warning"


def test_snapshot_preserves_previous_run_on_staging_failure_and_protects_resources(
    tmp_path,
):
    destination = tmp_path / "report.artifacts"
    destination.mkdir()
    original = destination / "original.txt"
    original.write_text("original")
    source = tmp_path / "source.txt"
    source.write_text("replacement")

    class BrokenStore:
        def publish(self, *args):
            raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        publish_snapshot(
            BrokenStore(), [(source, Path("replacement.txt"))], destination, set()
        )
    assert original.read_text() == "original"
    with pytest.raises(ValueError, match="overwrite template resources"):
        publish_snapshot(LocalArtifactStore(), [], destination, {original})
    assert original.read_text() == "original"


def test_converter_caches_version_and_passes_only_isolated_environment(
    tmp_path, monkeypatch
):
    probes = []
    environments = []
    monkeypatch.setenv("REPORT_SECRET", "must-not-propagate")

    def probe(command, **kwargs):
        probes.append(command)
        environments.append(kwargs["env"])
        return SimpleNamespace(stdout=b"Test Office 24.2\n")

    def launch(command, **kwargs):
        environments.append(kwargs["env"])
        outdir = Path(command[command.index("--outdir") + 1])
        (outdir / "source.docx").write_bytes(b"output")
        return SimpleNamespace(
            returncode=0, communicate=lambda **kwargs: (b"converted", None)
        )

    monkeypatch.setattr(subprocess, "run", probe)
    monkeypatch.setattr(subprocess, "Popen", launch)
    converter = LibreOfficeConverter()
    source = tmp_path / "source.fodt"
    source.write_text("<document/>")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda i: converter.convert(source, "docx", tmp_path / str(i)), range(2)
            )
        )
    assert all(p.is_file() for p in results)
    assert len(probes) == 1
    for environment in environments:
        assert "HOME" not in environment and "REPORT_SECRET" not in environment
        assert Path(environment["XDG_CONFIG_HOME"]).is_relative_to(tmp_path)
        assert Path(environment["XDG_CACHE_HOME"]).is_dir()
    assert (tmp_path / "1/version.txt").read_text() == "Test Office 24.2"


def test_keyboard_interrupt_kills_without_draining_pipe(tmp_path, monkeypatch):
    class Process:
        calls = 0
        killed = False
        stdout = io.BytesIO()

        def communicate(self, **kwargs):
            self.calls += 1
            raise KeyboardInterrupt

        def wait(self, **kwargs):
            assert self.killed

    process = Process()
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout=b"Test Office")
    )
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: process)
    monkeypatch.setattr(
        LibreOfficeConverter,
        "_kill",
        staticmethod(lambda p: setattr(p, "killed", True)),
    )
    with pytest.raises(KeyboardInterrupt):
        LibreOfficeConverter().convert(
            tmp_path / "source.fodt", "docx", tmp_path / "export"
        )
    assert process.killed and process.calls == 1 and process.stdout.closed


@pytest.mark.parametrize(
    "tag", ["office:dde-source", "table:dde-link", "text:dde-connection-decls"]
)
def test_dde_sources_rejected(tag):
    source = (ROOT / "examples/office_xlsx/main.fods").read_text()
    source = source.replace("<office:spreadsheet>", f"<office:spreadsheet><{tag}/>")
    with pytest.raises(ValueError, match="DDE"):
        OdfTemplate(source, "xlsx")


@pytest.mark.parametrize(
    "formula",
    [
        "WEBSERVICE(&quot;https://example.com&quot;)",
        "com.microsoft.webservice (1)",
        "DDE(1;2;3)",
        "HYPERLINK(1)",
    ],
)
def test_external_data_formulas_rejected(formula):
    source = (ROOT / "examples/office_xlsx/main.fods").read_text()
    source = source.replace("SUM([Sales.B2:Sales.B4])", formula)
    with pytest.raises(ValueError, match="External-data"):
        OdfTemplate(source, "xlsx")


def test_function_names_inside_formula_string_literals_are_not_calls():
    source = (ROOT / "examples/office_xlsx/main.fods").read_text()
    OdfTemplate(
        source.replace("SUM([Sales.B2:Sales.B4])", "&quot;WEBSERVICE(&quot;"), "xlsx"
    )


@pytest.mark.parametrize("level", ["slide", "layout", "master", "unreferenced"])
def test_animation_verification_follows_slide_layout_and_master_relationships(
    tmp_path, level
):
    gif = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(
        gif,
        format="GIF",
        save_all=True,
        append_images=[Image.new("RGB", (4, 4), "blue")],
        duration=100,
        loop=0,
    )

    def relationships(targets):
        return (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="r{i}" Target="{target}" Type="test"/>'
                for i, target in enumerate(targets)
            )
            + "</Relationships>"
        )

    path = tmp_path / "deck.pptx"
    with ZipFile(path, "w") as archive:
        for name in [
            "[Content_Types].xml",
            "ppt/presentation.xml",
            "ppt/slides/slide1.xml",
            "ppt/slideLayouts/layout1.xml",
            "ppt/slideMasters/master1.xml",
        ]:
            archive.writestr(name, "<document/>")
        archive.writestr("_rels/.rels", relationships(["ppt/presentation.xml"]))
        archive.writestr(
            "ppt/_rels/presentation.xml.rels", relationships(["slides/slide1.xml"])
        )
        for label, part, target in [
            ("slide", "slides/slide1", "../slideLayouts/layout1.xml"),
            ("layout", "slideLayouts/layout1", "../slideMasters/master1.xml"),
            ("master", "slideMasters/master1", "../slideLayouts/layout1.xml"),
        ]:
            folder, filename = part.split("/")
            targets = [target] + (["../media/chart.gif"] if label == level else [])
            archive.writestr(
                f"ppt/{folder}/_rels/{filename}.xml.rels", relationships(targets)
            )
        archive.writestr("ppt/media/chart.gif", gif.getvalue())
    if level == "unreferenced":
        with pytest.raises(ConversionError, match="preserve"):
            verify_package(path, "pptx", [gif.getvalue()])
    else:
        verify_package(path, "pptx", [gif.getvalue()])
