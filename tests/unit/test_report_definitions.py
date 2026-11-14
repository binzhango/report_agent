"""Report contracts and onboarding enforce reusable, confirmed executions."""

import pandas as pd
import pytest

from report_agent.application.onboarding import Onboarding, OnboardingService
from report_agent.application.report_runs import ReportRuns
from report_agent.definitions.bindings import bind_queries
from report_agent.definitions.models import ReportDefinition
from report_agent.definitions.parameters import Parameter, resolve_parameters
from report_agent.models.results import RenderResult
from report_agent.storage.report_definitions import ReportStore


def sales_definition(fmt="docx"):
    return ReportDefinition.model_validate(
        {
            "id": "monthly_sales",
            "name": "Monthly sales",
            "layout": {
                "title": "Sales",
                "format": fmt,
                "blocks": [
                    {
                        "name": "intro",
                        "heading": "Overview",
                        "text": "Fixed introduction.",
                    },
                    {"name": "sales", "kind": "table", "heading": "Sales by region"},
                ],
            },
            "parameters": {
                "start": {"type": "date"},
                "end": {"type": "date"},
                "region": {"type": "string", "default": "Europe"},
            },
            "parameter_order": [{"before": "start", "after": "end"}],
            "text_bindings": {"title": "Sales for {region}: {start} to {end}"},
            "queries": {
                "sales": {
                    "connection": "db",
                    "query": (
                        "SELECT * FROM sales WHERE day >= :start "
                        "AND day < :end AND region = :region"
                    ),
                    "parameter_bindings": {
                        "start": "start",
                        "end": "end",
                        "region": "region",
                    },
                    "columns": ["region", "revenue"],
                }
            },
        }
    )


class RecordingRenderer:
    def __init__(self):
        self.requests = []

    def render(self, request):
        self.requests.append(request)
        request.output.write_bytes(b"test report")
        return RenderResult(output_path=request.output)


def test_parameter_types_defaults_and_date_boundaries():
    definition = sales_definition()
    params, queries = bind_queries(
        definition, {"start": "2026-10-01", "end": "2026-11-01"}
    )
    assert params["region"] == "Europe"
    assert queries["sales"].query == definition.queries["sales"].query
    assert queries["sales"].params == params
    for supplied in [
        {"start": "2026-11-01", "end": "2026-10-01"},
        {"start": "2026-02-30", "end": "2026-03-01"},
        {"start": "2026-10-01"},
        {"start": "2026-10-01", "end": "2026-11-01", "unknown": "x"},
    ]:
        with pytest.raises(ValueError):
            bind_queries(definition, supplied)
    with pytest.raises(ValueError):
        resolve_parameters({"count": Parameter(type="integer")}, {"count": True})
    with pytest.raises(ValueError):
        resolve_parameters(
            {"amount": Parameter(type="number")}, {"amount": float("nan")}
        )


@pytest.mark.parametrize(
    "binding", ["{region.__class__}", "{region!r}", "{region:>30}", "{missing}"]
)
def test_text_binding_rejects_expressions(binding):
    data = sales_definition().model_dump()
    data["text_bindings"]["title"] = binding
    with pytest.raises(ValueError):
        ReportDefinition.model_validate(data)


def test_confirmation_reuses_accepted_bundle_with_new_parameters(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "report_agent.application.onboarding.thumbnails", lambda result: []
    )
    store = ReportStore(tmp_path / "library")
    renderer = RecordingRenderer()
    fetched = []

    class Source:
        def fetch(self, query):
            fetched.append(query)
            return pd.DataFrame({"region": [query.params["region"]], "revenue": [123]})

    runs = ReportRuns(store, {"db": Source()}, tmp_path / "output", renderer=renderer)
    service = OnboardingService(store, runs)
    session = Onboarding()
    draft = service.stage(session, sales_definition().model_dump())
    with pytest.raises(ValueError, match="Preview"):
        service.accept(session)
    first = {"start": "2026-10-01", "end": "2026-11-01"}
    assert service.preview(session, draft, first)["success"]
    assert session.preview_queries["parameters"] == {**first, "region": "Europe"}
    with pytest.raises(ValueError, match="Review the queries"):
        service.accept(session)
    assert (
        session.preview_queries["queries"]["sales"]["query"]
        == sales_definition().queries["sales"].query
    )
    accepted = service.accept(session, queries_reviewed=True)
    before = {
        p.name: p.read_bytes() for p in store.path(accepted).iterdir() if p.is_file()
    }
    second = {"start": "2026-11-01", "end": "2026-12-01", "region": "Asia"}
    proposal = service.propose(session, accepted, second)
    assert proposal["parameters"] == second
    assert len(fetched) == 1  # No query is executed before confirmation.
    result = service.confirm(session)
    assert result.output_path
    assert fetched[-1].params == second
    assert fetched[0].query == fetched[-1].query
    assert renderer.requests[-1].inputs["title"].text.startswith("Sales for Asia")
    assert "intro" not in renderer.requests[-1].inputs  # Metadata owns fixed text.
    assert session.pending is None
    assert before == {
        p.name: p.read_bytes() for p in store.path(accepted).iterdir() if p.is_file()
    }
    with pytest.raises(ValueError, match="prepare"):
        service.confirm(session)
    service.stage(session, sales_definition().model_dump())
    with pytest.raises(ValueError, match="Preview"):
        service.accept(session)


def test_path_traversal_and_query_failure_do_not_publish(tmp_path):
    store = ReportStore(tmp_path / "library")
    with pytest.raises(ValueError):
        store.path("../../secret")
    definition = sales_definition()
    ref = store.draft(definition)
    renderer = RecordingRenderer()

    class EmptySource:
        def fetch(self, query):
            return pd.DataFrame()

    runs = ReportRuns(
        store, {"db": EmptySource()}, tmp_path / "output", renderer=renderer
    )
    with pytest.raises(ValueError, match="no rows"):
        runs.run(ref, {"start": "2026-10-01", "end": "2026-11-01"})
    assert not renderer.requests
    assert len(list((tmp_path / "output").glob("*/run.json"))) == 1


def test_file_filters_are_saved_with_report_not_mutated_on_shared_source(tmp_path):
    from report_agent.connectors.files import FileSource

    path = tmp_path / "sales.csv"
    path.write_text(
        "day,region,revenue\n2026-10-15,Europe,120\n2026-11-15,Europe,150\n"
    )
    definition = sales_definition().model_dump()
    definition["queries"]["sales"].update(
        connection="file",
        query="data",
        filters={
            "start": {"column": "day", "op": "ge", "type": "date"},
            "end": {"column": "day", "op": "lt", "type": "date"},
            "region": {"column": "region", "op": "eq"},
        },
    )
    store = ReportStore(tmp_path / "library")
    reference = store.draft(ReportDefinition.model_validate(definition))
    source = FileSource(path)
    renderer = RecordingRenderer()
    runs = ReportRuns(store, {"file": source}, tmp_path / "output", renderer=renderer)
    runs.run(reference, {"start": "2026-10-01", "end": "2026-11-01"})
    assert renderer.requests[-1].inputs["sales"].data.revenue.tolist() == [120]
    assert list(renderer.requests[-1].inputs["sales"].data.columns) == [
        "region",
        "revenue",
    ]  # Filter columns must not leak into the rendered table.
    runs.run(reference, {"start": "2026-11-01", "end": "2026-12-01"})
    assert renderer.requests[-1].inputs["sales"].data.revenue.tolist() == [150]
    assert source.filters == {}
