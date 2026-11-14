"""Build orchestration, validation, publication, and cleanup contracts."""

from pathlib import Path

import pytest

from report_agent import ImageInput, RenderRequest, TextInput
from report_agent.application.service import ReportRenderer
from report_agent.application.validation import RenderValidator
from report_agent.metadata.loader import MetadataLoader
from report_agent.metadata.models import CompilerOptions
from report_agent.models.results import CompileResult, Diagnostic
from report_agent.presentation.styler import LatexPlaceholderStyler
from report_agent.rendering.registry import RendererRegistry
from report_agent.rendering.text import TextRenderer
from report_agent.storage.artifacts import LocalArtifactStore
from report_agent.storage.workspace import TemporaryWorkspaceManager
from report_agent.templates.engine import JinjaTemplateEngine
from report_agent.templates.repository import LocalTemplateRepository


class RecordingCompiler:
    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.source = ""
        self.fail = fail

    def compile(self, entrypoint: Path, options: CompilerOptions) -> CompileResult:
        self.calls += 1
        self.source = entrypoint.read_text()
        assert (entrypoint.parent / "static.tex").read_text() == "Static resource"
        log = entrypoint.with_suffix(".log")
        log.write_text("Compiler transcript")
        if self.fail:
            return CompileResult(
                None, (Diagnostic("compilation", "test_failure", "Broken TeX"),), log
            )
        pdf = entrypoint.with_suffix(".pdf")
        pdf.write_bytes(b"%PDF-test")
        return CompileResult(pdf, log_path=log)


@pytest.fixture
def build(tmp_path: Path):
    root = tmp_path / "template"
    root.mkdir()
    (root / "main.tex").write_text("<<title>>\n<<period>>\n<<footer>>")
    (root / "static.tex").write_text("Static resource")
    metadata = {
        "id": "test",
        "inputs": {
            "title": {"type": "text", "max_chars": 20},
            "period": {"type": "text", "default": "Q3 & Q4"},
            "footer": {"type": "text", "required": False},
        },
    }
    compiler = RecordingCompiler()
    engine = JinjaTemplateEngine()
    workspaces = tmp_path / "workspaces"
    registry = RendererRegistry({("text", None): TextRenderer()})
    renderer = ReportRenderer(
        metadata_loader=MetadataLoader(),
        templates=LocalTemplateRepository(),
        validator=RenderValidator(engine, registry),
        renderers=registry,
        template_engine=engine,
        compiler=compiler,
        workspaces=TemporaryWorkspaceManager(workspaces),
        artifacts=LocalArtifactStore(),
        styler=LatexPlaceholderStyler(),
    )
    request = RenderRequest(
        root,
        metadata,
        {"title": TextInput("Sales & costs")},
        tmp_path / "out/report.pdf",
    )
    return renderer, request, compiler, workspaces


def test_pipeline_applies_defaults_publishes_and_cleans_workspace(build) -> None:
    renderer, request, compiler, workspaces = build
    original = (request.template / "main.tex").read_text()
    result = renderer.render(request)
    assert result.pdf_path == request.output
    assert result.pdf_path.read_bytes() == b"%PDF-test"
    assert compiler.source == "Sales \\& costs\nQ3 \\& Q4\n"
    assert all(path.is_file() for path in result.artifacts)
    assert list(workspaces.iterdir()) == []
    assert (request.template / "main.tex").read_text() == original


def test_pdf_render_resolves_agent_text_and_replaces_artifacts(build):
    from dataclasses import replace

    from report_agent.resolution import ContentResolver

    renderer, request, compiler, workspaces = build

    class Generator:
        def generate(self, request):
            return "Generated title"

    renderer._resolver = ContentResolver(sources={}, text_generator=Generator())
    request.metadata["inputs"]["title"].update(source="agent", prompt="Write a title")
    request = replace(request, inputs={})
    result = renderer.render(request)
    assert result.output_path and "Generated title" in compiler.source
    stale = request.output.parent / "report.artifacts/stale.log"
    stale.write_text("previous run")
    assert renderer.render(request).output_path
    assert not stale.exists()
    assert list(workspaces.iterdir()) == []


@pytest.mark.parametrize(
    "text", ["bad\ufffeX", "bad\uffffX", "bad\ud800X", "bad\udfffX"]
)
def test_pdf_rejects_invalid_xml_characters_before_compilation(build, text):
    from dataclasses import replace

    renderer, request, compiler, _ = build
    result = renderer.render(replace(request, inputs={"title": TextInput(text)}))
    issue = result.diagnostics[0]
    assert (issue.stage, issue.code, issue.input_name) == (
        "input_validation",
        "invalid_text",
        "title",
    )
    assert compiler.calls == 0


@pytest.mark.parametrize(
    "inputs, code",
    [
        ({}, "missing_input"),
        ({"title": "raw string"}, "input_type"),
        ({"title": TextInput("x" * 21)}, "text_length"),
        ({"title": TextInput("Title"), "extra": TextInput("extra")}, "unknown_input"),
    ],
)
def test_invalid_inputs_never_reach_compiler(build, inputs, code) -> None:
    renderer, request, compiler, _ = build
    request = RenderRequest(request.template, request.metadata, inputs, request.output)
    result = renderer.render(request)
    assert result.pdf_path is None
    assert code in {item.code for item in result.diagnostics}
    assert compiler.calls == 0
    assert not request.output.exists()


def test_placeholder_mismatch_fails_before_compilation(build) -> None:
    renderer, request, compiler, _ = build
    (request.template / "main.tex").write_text("<<undeclared>>")
    result = renderer.render(request)
    assert {item.code for item in result.diagnostics} == {
        "undeclared_placeholder",
        "unused_input",
    }
    assert compiler.calls == 0


def test_missing_renderer_strategy_has_structured_error(build) -> None:
    renderer, request, compiler, _ = build
    request.metadata["inputs"]["title"] = {"type": "image"}
    request = RenderRequest(
        request.template,
        request.metadata,
        {"title": ImageInput(Path("logo.png"))},
        request.output,
    )
    result = renderer.render(request)
    assert result.diagnostics[0].code == "unsupported_backend"
    assert "No renderer registered" in result.diagnostics[0].message
    assert result.diagnostics[0].input_name == "title"
    assert compiler.calls == 0


def test_compile_failure_retains_diagnostics_and_previous_pdf(build) -> None:
    renderer, request, compiler, workspaces = build
    compiler.fail = True
    request.output.parent.mkdir()
    request.output.write_bytes(b"Previous report")
    result = renderer.render(request)
    assert result.pdf_path is None
    assert result.diagnostics[0].code == "test_failure"
    assert request.output.read_bytes() == b"Previous report"
    assert {path.name for path in result.artifacts} == {
        "main.tex",
        "compile.log",
        "static.tex",
    }
    assert all(path.is_file() for path in result.artifacts)
    assert list(workspaces.iterdir()) == []


def test_bad_text_cleans_workspace_and_identifies_input(build) -> None:
    renderer, request, compiler, workspaces = build
    request = RenderRequest(
        request.template,
        request.metadata,
        {"title": TextInput("bad\x00")},
        request.output,
    )
    result = renderer.render(request)
    assert result.diagnostics[0].input_name == "title"
    assert compiler.calls == 0
    assert not workspaces.exists()


def test_missing_package_is_reported_per_input_before_compiling(build) -> None:
    renderer, request, compiler, _ = build
    request.metadata["inputs"]["title"]["style"] = {"typography": {"color": "#18343D"}}
    result = renderer.render(request)
    assert result.pdf_path is None
    assert result.diagnostics[0].code == "missing_package"
    assert result.diagnostics[0].input_name == "title"
    assert "xcolor" in result.diagnostics[0].message
    assert "provided_packages" in result.diagnostics[0].message
    assert compiler.calls == 0


def test_external_package_manifest_is_honored(build) -> None:
    renderer, request, _, _ = build
    request.metadata["inputs"]["title"]["style"] = {"typography": {"color": "#18343D"}}
    request.metadata["provided_packages"] = ["xcolor"]
    assert renderer.render(request).pdf_path is not None


def test_unexpected_content_exception_returns_input_diagnostic(
    build, monkeypatch, caplog
) -> None:
    renderer, request, compiler, _ = build

    def fail(*args, **kwargs):
        raise TypeError("unsupported dtype")

    monkeypatch.setattr(TextRenderer, "render", fail)
    result = renderer.render(request)
    assert result.pdf_path is None
    assert result.diagnostics[0].code == "internal_error"
    assert result.diagnostics[0].input_name == "title"
    assert compiler.calls == 0
    assert any(
        record.exc_info and "title" in record.getMessage() for record in caplog.records
    )


def test_unexpected_compiler_exception_returns_diagnostic(build, monkeypatch) -> None:
    renderer, request, compiler, _ = build

    def fail(*args, **kwargs):
        raise KeyError("unexpected")

    monkeypatch.setattr(compiler, "compile", fail)
    result = renderer.render(request)
    assert result.diagnostics[0].code == "internal_error"
    assert result.diagnostics[0].stage == "compilation"


def test_omitted_optional_backend_is_checked_before_compilation(build) -> None:
    renderer, request, compiler, _ = build
    request.metadata["inputs"]["footer"].update(type="table", backend="great_tables")
    result = renderer.render(request)
    assert any(
        issue.code == "unsupported_backend" and issue.input_name == "footer"
        for issue in result.diagnostics
    )
    assert compiler.calls == 0


def test_hidden_inputs_cannot_appear_in_template(build) -> None:
    renderer, request, compiler, _ = build
    request.metadata["inputs"]["footer"].update(type="table", visible=False)
    request.metadata["inputs"]["title"].update(
        source="agent", prompt="Summarize footer", uses=["footer"]
    )
    result = renderer.render(request)
    assert any(issue.code == "hidden_placeholder" for issue in result.diagnostics)
    assert compiler.calls == 0


def test_invalid_yaml_returns_structured_metadata_error(build, tmp_path: Path) -> None:
    renderer, request, compiler, _ = build
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("inputs: [unterminated")
    result = renderer.render(
        RenderRequest(request.template, invalid, request.inputs, request.output)
    )
    assert result.pdf_path is None
    assert result.diagnostics[0].stage == "metadata"
    assert "Invalid YAML" in result.diagnostics[0].message
    assert compiler.calls == 0


def test_nested_entrypoint_is_retained_at_its_relative_path(build) -> None:
    renderer, request, _, _ = build
    section = request.template / "sections"
    section.mkdir()
    (request.template / "main.tex").rename(section / "main.tex")
    (request.template / "static.tex").rename(section / "static.tex")
    request.metadata["entrypoint"] = "sections/main.tex"
    result = renderer.render(request)
    assert result.pdf_path is not None, result.diagnostics
    retained = request.output.parent / "report.artifacts"
    assert (retained / "sections/main.tex").is_file()
    assert (retained / "sections/static.tex").is_file()
    assert not (retained / "main.tex").exists()


def test_artifact_paths_cannot_overwrite_original_template(build) -> None:
    renderer, request, _, _ = build
    output = request.template.parent / "template.pdf"
    renamed = request.template.with_name("template.artifacts")
    request.template.rename(renamed)
    source = (renamed / "main.tex").read_text()
    result = renderer.render(
        RenderRequest(renamed, request.metadata, request.inputs, output)
    )
    assert result.pdf_path is None
    assert "overwrite template resources" in result.diagnostics[0].message
    assert (renamed / "main.tex").read_text() == source


@pytest.mark.parametrize("alias", [False, True])
def test_output_pdf_cannot_overwrite_template_resource(build, alias) -> None:
    renderer, request, compiler, workspaces = build
    resource = request.template / "reference.pdf"
    resource.write_bytes(b"%PDF-original resource")
    output = resource
    if alias:
        request.output.parent.mkdir()
        output = request.output
        output.symlink_to(resource)
    result = renderer.render(
        RenderRequest(request.template, request.metadata, request.inputs, output)
    )
    assert result.pdf_path is None
    assert result.diagnostics[0].stage == "output_validation"
    assert "overwrite template resources" in result.diagnostics[0].message
    assert resource.read_bytes() == b"%PDF-original resource"
    assert compiler.calls == 0
    assert not workspaces.exists()
