"""Resolution runs inside normal render/CLI calls and owns generated media."""

import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest
from typer.testing import CliRunner

from report_agent import (
    AnimationInput,
    RenderRequest,
    TableInput,
    TextInput,
    create_renderer,
)
from report_agent.interfaces.cli.app import app
from report_agent.interfaces.cli.resolution import load_queries, load_resolver
from report_agent.metadata.loader import MetadataLoader
from report_agent.models.results import Diagnostic, RenderResult
from report_agent.resolution import ContentResolver, QuerySource

ROOT = Path(__file__).resolve().parents[2]


class RecordingBackend:
    def render(self, request, metadata):
        self.inputs = request.inputs
        for value in request.inputs.values():
            if isinstance(value, AnimationInput):
                assert value.path.is_file() and value.poster_path.is_file()
        return RenderResult(output_path=request.output)


def agent_metadata():
    metadata = (
        MetadataLoader().load(ROOT / "examples/office_docx/template.yaml").model_dump()
    )
    metadata["inputs"]["summary"].update(
        source="agent", prompt="Summarize sales", uses=["sales"], max_chars=100
    )
    return metadata


def test_render_fetches_then_generates_and_preserves_supplied_override(tmp_path):
    calls = []

    class Source:
        def fetch(self, query):
            calls.append("query")
            return pd.DataFrame({"Revenue": [4, 7]})

    class Generator:
        def generate(self, request):
            calls.append("agent")
            assert request.tables["sales"].row_count == 2
            return "Revenue was 11."

    backend = RecordingBackend()
    renderer = create_renderer(
        office_backend=backend,
        resolver=ContentResolver(
            sources={"demo": Source()}, text_generator=Generator()
        ),
    )
    request = RenderRequest(
        ROOT / "examples/office_docx",
        agent_metadata(),
        {"title": TextInput("Review")},
        tmp_path / "review.docx",
        queries={"sales": QuerySource(connection="demo", query="sales")},
    )
    assert renderer.render(request).output_path
    assert calls == ["query", "agent"]
    assert backend.inputs["summary"] == TextInput("Revenue was 11.")
    assert set(request.inputs) == {"title"}
    calls.clear()
    assert renderer.render(
        replace(request, inputs={**request.inputs, "summary": TextInput("Reviewed")})
    ).output_path
    assert calls == ["query"]
    assert backend.inputs["summary"] == TextInput("Reviewed")


@pytest.mark.parametrize("failed", [False, True])
def test_generated_media_lives_through_render_then_is_cleaned(tmp_path, failed):
    class Generator:
        def generate(self, name, tables, options, directory):
            directory.mkdir()
            self.asset = AnimationInput(
                directory / "chart.gif", directory / "poster.png"
            )
            self.asset.path.write_bytes(b"gif")
            self.asset.poster_path.write_bytes(b"png")
            return self.asset

    class Backend(RecordingBackend):
        def render(self, request, metadata):
            result = super().render(request, metadata)
            return (
                RenderResult(diagnostics=(Diagnostic("conversion", "test", "failed"),))
                if failed
                else result
            )

    registry = Generator()
    backend = Backend()
    renderer = create_renderer(
        office_backend=backend,
        resolver=ContentResolver(sources={}, animation_generators=registry),
    )
    result = renderer.render(
        RenderRequest(
            ROOT / "examples/office_pptx",
            ROOT / "examples/office_pptx/template.yaml",
            {"sales_data": TableInput(pd.DataFrame({"sales": [1]}))},
            tmp_path / "report.pptx",
        )
    )
    assert bool(result.output_path) is not failed
    assert not registry.asset.path.parent.exists()


def test_missing_adapter_and_resolution_errors_stop_backend(tmp_path):
    backend = RecordingBackend()
    renderer = create_renderer(office_backend=backend)
    result = renderer.render(
        RenderRequest(
            ROOT / "examples/office_docx",
            agent_metadata(),
            {},
            tmp_path / "review.docx",
        )
    )
    assert result.diagnostics[0].stage == "resolution"
    assert result.diagnostics[0].code == "resolution_failed"
    assert result.diagnostics[0].input_name == "summary"
    assert "injected text generator" in result.diagnostics[0].message
    assert not hasattr(backend, "inputs")


def test_cli_resolver_factory_and_query_bindings(tmp_path, monkeypatch):
    import report_agent.interfaces.cli.app as cli_module

    class Source:
        def fetch(self, query):
            assert query.params == {"period": "Q3"} and query.row_limit == 10
            return pd.DataFrame({"sales": [12]})

    class Generator:
        def generate(self, request):
            return "CLI-generated summary"

    module = ModuleType("report_test_adapters")
    module.make_resolver = lambda: ContentResolver(
        sources={"demo": Source()}, text_generator=Generator()
    )
    monkeypatch.setitem(sys.modules, module.__name__, module)
    backend = RecordingBackend()
    monkeypatch.setattr(
        cli_module,
        "create_renderer",
        lambda **kw: create_renderer(office_backend=backend, **kw),
    )
    import yaml

    metadata = tmp_path / "template.yaml"
    metadata.write_text(yaml.safe_dump(agent_metadata()))
    queries = tmp_path / "queries.yaml"
    queries.write_text(
        "queries:\n  sales:\n    connection: demo\n    query: sales\n"
        "    params: {period: Q3}\n    row_limit: 10\n"
    )
    result = CliRunner().invoke(
        app,
        [
            "render",
            str(ROOT / "examples/office_docx"),
            "--metadata",
            str(metadata),
            "--output",
            str(tmp_path / "review.docx"),
            "--text",
            "title=Review",
            "--resolver",
            "report_test_adapters:make_resolver",
            "--queries",
            str(queries),
        ],
    )
    assert result.exit_code == 0, result.output
    assert backend.inputs["summary"] == TextInput("CLI-generated summary")
    assert backend.inputs["sales"].data.iloc[0, 0] == 12


def test_cli_resolution_configuration_is_explicit_and_strict(tmp_path):
    with pytest.raises(ValueError, match="module:factory"):
        load_resolver("no_factory")
    with pytest.raises(ValueError, match="ContentResolver"):
        load_resolver("builtins:dict")
    queries = tmp_path / "queries.yaml"
    queries.write_text("queries: {}\nqueries: {}\n")
    with pytest.raises(ValueError, match="Duplicate"):
        load_queries(queries)
    queries.write_text("queries: {}\nresolver: untrusted:factory\n")
    with pytest.raises(ValueError, match="mapping only"):
        load_queries(queries)
