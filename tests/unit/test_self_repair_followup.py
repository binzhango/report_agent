"""Regression cases from review: actionable errors, budgets, and month arithmetic."""

import json
import logging
from pathlib import Path

import pytest

pytest.importorskip("deepagents")

from report_agent.agent.config import AgentConfig
from report_agent.agent.errors import public_tool_error
from report_agent.agent.tools.reports import build_tools
from report_agent.application.conversation import ConversationService
from report_agent.application.input_forms import parameter_form
from report_agent.application.onboarding import Onboarding, OnboardingService
from report_agent.application.report_runs import ReportRuns
from report_agent.definitions.calendar_months import (
    calendar_ranges,
    expand_report_month,
    month_dates,
)
from report_agent.definitions.models import ReportDefinition
from report_agent.definitions.parameters import DateRange
from report_agent.errors import ReportError
from report_agent.interfaces.gradio.input_forms import (
    month_input_state,
    unpack_form_answers,
)
from report_agent.storage.report_definitions import ReportStore


def base():
    return {
        "id": "monthly",
        "name": "Monthly",
        "layout": {"title": "Monthly", "blocks": [{"name": "intro"}]},
    }


@pytest.fixture
def service(tmp_path):
    store = ReportStore(tmp_path / "library")
    onboarding = OnboardingService(store, ReportRuns(store, {}, tmp_path / "runs"))
    return ConversationService(
        AgentConfig("offline", Path(".agents/skills")),
        onboarding,
        {},
        agent_factory=lambda *args: None,
    )


def toolset(service, session):
    return {
        t.name: t for t in build_tools(session, service.onboarding, service.sources)
    }


def invalid_definition(case):
    data = base()
    if case == "duplicate":
        data["layout"]["blocks"] *= 2
    elif case == "reserved":
        data["layout"]["blocks"][0]["name"] = "title"
    elif case == "reserved_heading":
        data["layout"]["blocks"][0]["name"] = "heading_intro"
    elif case == "xlsx_chart":
        data["layout"].update(format="xlsx", blocks=[{"name": "plot", "kind": "chart"}])
    elif case == "missing_query":
        data["layout"]["blocks"][0]["kind"] = "table"
    elif case == "missing_chart":
        data["layout"]["blocks"][0]["kind"] = "chart"
    elif case == "chart_block":
        data["charts"] = {"intro": {"table": "rows", "x": "a", "y": "b"}}
    elif case == "chart_source":
        data["layout"]["blocks"][0]["kind"] = "chart"
        data["charts"] = {"intro": {"table": "rows", "x": "a", "y": "b"}}
    elif case in {"query_conflict", "query_parameters", "query_name"}:
        key = (
            "intro"
            if case == "query_conflict"
            else "bad/name"
            if case == "query_name"
            else "rows"
        )
        data["queries"] = {key: {"connection": "db", "query": "SELECT 1"}}
        if case == "query_parameters":
            data["queries"][key]["parameter_bindings"] = {"missing": "missing"}
    elif case == "parameter_name":
        data["parameters"] = {"bad/name": {"type": "string"}}
    elif case == "text_target":
        data["text_bindings"] = {"missing": "text"}
    elif case == "text_expression":
        data["text_bindings"] = {"intro": "{region.__class__}"}
    elif case == "text_braces":
        data["text_bindings"] = {"intro": "{"}
    elif case == "order_unknown":
        data["parameter_order"] = [{"before": "start", "after": "end"}]
    elif case == "order_types":
        data["parameters"] = {"start": {"type": "date"}, "end": {"type": "string"}}
        data["parameter_order"] = [{"before": "start", "after": "end"}]
    elif case == "range_unknown":
        data["date_ranges"] = [{"start": "start", "end": "end"}]
    elif case in {"range_type", "range_order", "range_overlap"}:
        data["parameters"] = {
            "start": {"type": "date"},
            "end": {"type": "string" if case == "range_type" else "date"},
        }
        data["date_ranges"] = [{"start": "start", "end": "end"}]
        if case != "range_order":
            data["parameter_order"] = [{"before": "start", "after": "end"}]
        if case == "range_overlap":
            data["date_ranges"] *= 2
    elif case == "builtin_pattern":
        data["id"] = "private/file/path"
    elif case == "builtin_missing":
        data.pop("layout")
    elif case == "builtin_enum":
        data["layout"]["format"] = "unknown"
    return data


@pytest.mark.parametrize(
    "case",
    [
        "duplicate",
        "reserved",
        "reserved_heading",
        "xlsx_chart",
        "missing_query",
        "missing_chart",
        "chart_block",
        "chart_source",
        "query_conflict",
        "query_parameters",
        "query_name",
        "parameter_name",
        "text_target",
        "text_expression",
        "text_braces",
        "order_unknown",
        "order_types",
        "range_unknown",
        "range_type",
        "range_order",
        "range_overlap",
        "builtin_pattern",
        "builtin_missing",
        "builtin_enum",
    ],
)
def test_every_definition_failure_has_actionable_public_issues(service, case):
    session = Onboarding()
    result = toolset(service, session)["create_draft"].invoke(
        {"definition": invalid_definition(case)}
    )
    assert result["kind"] == "ValidationError", result
    assert result["error"]
    assert result["issues"]
    assert all(issue.get("error") and issue.get("code") for issue in result["issues"])
    assert "private/file/path" not in json.dumps(result)
    if case in {
        "duplicate",
        "reserved",
        "reserved_heading",
        "xlsx_chart",
        "missing_query",
    }:
        assert result["issues"][0]["code"] != "schema_value_error"


@pytest.mark.parametrize("all_fail", [False, True])
def test_gallery_counts_as_one_attempt_and_keeps_per_preset_failures(
    service, monkeypatch, all_fail
):
    session = Onboarding()
    calls = []

    def preview(*args):
        calls.append(args)
        return {
            "success": False if all_fail or len(calls) == 1 else True,
            "diagnostics": [],
        }

    monkeypatch.setattr(service.onboarding, "preview", preview)
    tools = toolset(service, session)
    result = tools["rendered_examples"].invoke(
        {"output_format": "docx", "topic": "Project update"}
    )
    assert len(calls) == len(result) == 3
    assert result[0]["success"] is False
    assert session.repair_attempts == 0
    assert session.repair_pending is all_fail
    staged = tools["create_draft"].invoke({"definition": base()})
    assert "draft" in staged
    assert session.repair_attempts == int(all_fail)


def test_original_unexpected_exceptions_are_logged_but_not_returned(
    service, monkeypatch, caplog
):
    def crash(*args):
        raise RuntimeError("private-renderer-detail")

    monkeypatch.setattr(service.onboarding, "preview", crash)
    with caplog.at_level(logging.ERROR, logger="report_agent.agent.tools.reports"):
        result = toolset(service, Onboarding())["rendered_examples"].invoke(
            {"output_format": "docx", "topic": "Project update"}
        )
    assert len(result) == 3 and all(item["kind"] == "InternalError" for item in result)
    assert "private-renderer-detail" not in json.dumps(result)
    assert "private-renderer-detail" in caplog.text
    assert len([record for record in caplog.records if record.exc_info]) == 3


@pytest.mark.parametrize(
    "inclusive,month,start,end",
    [
        (False, "October 2026", "2026-10-01", "2026-11-01"),
        (False, "December 2026", "2026-12-01", "2027-01-01"),
        (False, "February 2024", "2024-02-01", "2024-03-01"),
        (True, "February 2024", "2024-02-01", "2024-02-29"),
        (True, "February 2025", "2025-02-01", "2025-02-28"),
    ],
)
def test_month_dates_handle_exclusive_inclusive_leap_and_year_boundaries(
    inclusive, month, start, end
):
    span = DateRange(start="start", end="end", end_inclusive=inclusive)
    assert month_dates(span, month) == {"start": start, "end": end}
    assert month_input_state(span, {"start": start, "end": end}) == ("month", start[:7])


def range_definition():
    data = base()
    data["parameters"] = {
        "start_date": {"type": "date"},
        "end_date": {"type": "date"},
        "region": {"type": "string"},
    }
    data["parameter_order"] = [{"before": "start_date", "after": "end_date"}]
    return ReportDefinition.model_validate(data)


def test_form_month_and_tool_month_derive_dates_without_model_or_queries(
    service, tmp_path
):
    definition = range_definition()
    store = service.onboarding.store
    draft = store.draft(definition)
    sample = tmp_path / "sample.docx"
    sample.write_bytes(b"fixture")
    accepted = store.accept(draft, sample)
    form = parameter_form(
        definition,
        accepted,
        {"region": "Europe"},
        title="Monthly report",
        description="",
    )
    assert form.month_ranges
    values = unpack_form_answers(
        form.model_dump(), [None, None, "Europe", "month", "October 2026"]
    )
    session = service.get_session(service.new_session())
    session.input_form = form.model_dump()
    service.submit_inputs(session.id, form.id, values)
    expected = {
        "start_date": "2026-10-01",
        "end_date": "2026-11-01",
        "region": "Europe",
    }
    assert session.pending["parameters"] == expected
    result = toolset(service, session)["propose_report_run"].invoke(
        {
            "reference": accepted,
            "parameters": {"region": "Europe"},
            "report_month": "October 2026",
        }
    )
    assert result["parameters"] == expected
    result = toolset(service, session)["propose_report_run"].invoke(
        {
            "reference": accepted,
            "parameters": {**expected, "end_date": "2026-10-31"},
            "report_month": "October 2026",
        }
    )
    assert result["code"] == "month_date_conflict"
    assert session.pending is None
    assert not service.agents
    assert (
        month_input_state(
            form.month_ranges[0], {"start_date": "2026-10-15", "end_date": "2026-11-01"}
        )[0]
        == "dates"
    )


@pytest.mark.parametrize(
    "operator,inclusive", [("<", False), ("<=", True), ("BETWEEN", True), ("=", None)]
)
def test_legacy_query_bound_semantics_are_preserved(operator, inclusive):
    definition = range_definition().model_dump()
    query = (
        "SELECT * FROM sales WHERE day BETWEEN :start AND :end"
        if operator == "BETWEEN"
        else f"SELECT * FROM sales WHERE day >= :start AND day {operator} :end"
    )
    definition["queries"] = {
        "rows": {
            "connection": "db",
            "query": query,
            "parameter_bindings": {"start": "start_date", "end": "end_date"},
        }
    }
    spans = calendar_ranges(ReportDefinition.model_validate(definition))
    assert len(spans) == (0 if inclusive is None else 1)
    if spans:
        assert spans[0].end_inclusive is inclusive


def test_conflicting_legacy_ranges_require_custom_dates():
    definition = range_definition().model_dump()
    definition["queries"] = {
        "rows": {
            "connection": "db",
            "query": "SELECT * FROM sales WHERE day < :end OR other_day <= :end",
            "parameter_bindings": {"end": "end_date"},
        }
    }
    definition = ReportDefinition.model_validate(definition)
    assert not calendar_ranges(definition)
    with pytest.raises(ReportError, match="parameter form"):
        expand_report_month(definition, {}, "October 2026")


@pytest.mark.parametrize("operator,inclusive", [("lt", False), ("le", True)])
def test_file_date_range_semantics_and_explicit_metadata(operator, inclusive):
    data = range_definition().model_dump()
    data["queries"] = {
        "rows": {
            "connection": "file",
            "query": "data",
            "parameter_bindings": {"start": "start_date", "end": "end_date"},
            "filters": {
                "start": {"column": "day", "op": "ge", "type": "date"},
                "end": {"column": "day", "op": operator, "type": "date"},
            },
        }
    }
    definition = ReportDefinition.model_validate(data)
    assert calendar_ranges(definition)[0].end_inclusive is inclusive
    data["date_ranges"] = [
        {"start": "start_date", "end": "end_date", "end_inclusive": inclusive}
    ]
    assert (
        calendar_ranges(ReportDefinition.model_validate(data))[0].end_inclusive
        is inclusive
    )
    data["date_ranges"][0]["end_inclusive"] = not inclusive
    with pytest.raises(ValueError, match="conflicts with the saved") as caught:
        ReportDefinition.model_validate(data)
    assert (
        public_tool_error(caught.value)["issues"][0]["code"]
        == "date_range_boundary_conflict"
    )


def test_connector_owned_errors_remain_actionable(service, tmp_path):
    from report_agent.connectors.files import FileSource
    from report_agent.connectors.http import HttpSource
    from report_agent.connectors.sql import SqlSource
    from report_agent.resolution.models import QuerySource

    oversized = tmp_path / "big.csv"
    with oversized.open("wb") as stream:
        stream.truncate(21 * 1024 * 1024)
    source = SqlSource("sqlite://")
    try:
        cases = [
            (
                lambda: FileSource(oversized).fetch(
                    QuerySource(
                        connection="file", query="data", params={"date": "2026-11-01"}
                    )
                ),
                "configured column filters",
            ),
            (
                lambda: FileSource(oversized).fetch(
                    QuerySource(connection="file", query="data")
                ),
                "20 MiB",
            ),
            (
                lambda: source.fetch(
                    QuerySource(
                        connection="db", query="SELECT 1", params={"_report_limit": 1}
                    )
                ),
                "_report_limit is reserved",
            ),
            (
                lambda: HttpSource({}).fetch(
                    QuerySource(connection="api", query="missing")
                ),
                "configured API endpoint",
            ),
        ]
        for action, message in cases:
            with pytest.raises(ReportError) as caught:
                action()
            error = public_tool_error(caught.value)
            assert error["kind"] == "ReportError" and message in error["error"]
    finally:
        source.engine.dispose()
