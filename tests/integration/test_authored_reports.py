"""Compile new layouts and inspect actual generated reports in all four formats."""

import shutil

import pytest

from report_agent.application.report_runs import ReportRuns
from report_agent.definitions.models import ReportDefinition
from report_agent.ingestion.samples import extract_sample
from report_agent.storage.report_definitions import ReportStore


@pytest.mark.parametrize("fmt", ["pdf", "docx", "pptx", "xlsx"])
def test_authored_layout_renders_and_can_be_uploaded_again(tmp_path, fmt):
    if not shutil.which("texres" if fmt == "pdf" else "soffice"):
        pytest.skip("Document engine is unavailable")
    if fmt == "pdf":
        pytest.importorskip("pypdf")
    definition = ReportDefinition.model_validate(
        {
            "id": "review",
            "name": "Review",
            "layout": {
                "title": "Regional revenue review",
                "format": fmt,
                "blocks": [
                    {
                        "name": "summary",
                        "heading": "Summary",
                        "text": "Fixed introduction and demonstration values.",
                    },
                    {"name": "sales", "heading": "Regional revenue", "kind": "table"},
                ],
            },
            "queries": {
                "sales": {
                    "connection": "demo",
                    "query": "data",
                    "columns": ["Region", "Revenue"],
                }
            },
        }
    )
    store = ReportStore(tmp_path / "library")
    reference = store.draft(definition)
    result = ReportRuns(store, {}, tmp_path / "output").run(
        reference,
        {},
        sample_tables={
            "sales": [
                {"Region": "Europe", "Revenue": 120},
                {"Region": "Asia", "Revenue": 90},
            ],
        },
    )
    assert result.output_path, result.diagnostics
    sample = extract_sample(result.output_path)
    assert "Regional revenue review" in sample["text"]
    assert "Fixed introduction" in sample["text"]
    assert "Europe" in sample["text"]
    assert "120" in sample["text"]
    accepted = store.accept(reference, result.output_path)
    assert store.load(accepted) == definition
    assert (store.path(accepted) / f"previews/sample.{fmt}").is_file()
