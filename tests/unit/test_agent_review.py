"""Regression coverage for report-agent review findings, without live providers."""

import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

pytest.importorskip("deepagents")

from langchain_core.messages import AIMessage
from pydantic import ValidationError

from report_agent.agent.catalog import ReportTemplate, catalog_context
from report_agent.agent.config import AgentConfig
from report_agent.agent.errors import public_tool_error
from report_agent.agent.tools.reports import build_tools
from report_agent.application.conversation import ConversationService
from report_agent.application.onboarding import Onboarding, OnboardingService
from report_agent.application.report_runs import ReportRuns
from report_agent.connectors.files import FileSource
from report_agent.connectors.registry import describe_source
from report_agent.definitions.models import ReportDefinition
from report_agent.ingestion import archives
from report_agent.resolution.models import QuerySource
from report_agent.storage.report_definitions import ReportStore


def make_service(tmp_path, response="Ready."):
    store = ReportStore(tmp_path / "library")
    onboarding = OnboardingService(store, ReportRuns(store, {}, tmp_path / "runs"))

    class Agent:
        def invoke(self, *args, **kwargs):
            return {"messages": [AIMessage(content=response)]}

    return ConversationService(
        AgentConfig("offline-test", tmp_path),
        onboarding,
        {},
        agent_factory=lambda *args: Agent(),
    )


def test_reference_names_do_not_corrupt_versions_or_replace_inside_names(tmp_path):
    response = (
        "Choose `accepted/sales/v1` or [accepted/sales/v10]. "
        "Keep accepted/sales/v100 and accepted/sales/v1/other."
    )
    service = make_service(tmp_path, response)
    key = service.new_session()
    session = service.get_session(key)
    session.candidates = {
        "Sales": "accepted/sales/v1",
        "Sales ten accepted/sales/v1": "accepted/sales/v10",
    }
    service.send(key, "Show designs")
    assert session.history[-1]["content"] == (
        "Choose `Sales` or [Sales ten accepted/sales/v1]. "
        "Keep accepted/sales/v100 and accepted/sales/v1/other."
    )


def test_inline_sql_and_normal_select_prose_are_preserved(tmp_path):
    response = (
        "Select items from your workbook. Example: `SELECT item FROM items`.\n"
        "```\nSelect the region you want from your workbook.\n```\n"
        "```text\nSELECT item FROM items\n```"
    )
    service = make_service(tmp_path, response)
    key = service.new_session()
    service.send(key, "Help me choose")
    assert service.get_session(key).history[-1]["content"] == response


@pytest.mark.parametrize(
    "query",
    [
        "SELECT 42 AS value -- trailing comment",
        "WITH result AS (SELECT 42 AS value) SELECT * FROM result -- comment",
        "SELECT 42 AS value /* block comment */",
        "SELECT 42 AS value;",
    ],
)
def test_sql_wrapper_handles_comments_and_ctes(query):
    from report_agent.connectors.sql import SqlSource

    source = SqlSource("sqlite://")
    try:
        result = source.fetch(QuerySource(connection="db", query=query))
        assert result.value.tolist() == [42]
        literal = source.fetch(
            QuerySource(connection="db", query="SELECT '-- literal' AS value -- end")
        )
        assert literal.value.tolist() == ["-- literal"]
    finally:
        source.engine.dispose()


def test_unknown_file_parameters_rejected_before_file_access(tmp_path):
    source = FileSource(tmp_path / "does-not-exist.xlsx")
    with pytest.raises(ValueError, match="filters"):
        source.fetch(QuerySource(connection="file", query="data", params={"bad": 1}))


@pytest.mark.parametrize("entry_limit", [False, True])
def test_oversized_xlsx_rejected_before_read_inspect_or_persist(
    tmp_path, monkeypatch, entry_limit
):
    path = tmp_path / "compressed.xlsx"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("one.xml", "x" * 80)
        archive.writestr("two.xml", "x" * 80)
    monkeypatch.setattr(
        archives, "MAX_EXPANDED_BYTES", 100 if not entry_limit else 1000
    )
    monkeypatch.setattr(archives, "MAX_ARCHIVE_ENTRIES", 1 if entry_limit else 3000)

    def unexpected_read(*args, **kwargs):
        pytest.fail("Workbook reader ran before the archive guard")

    monkeypatch.setattr("pandas.read_excel", unexpected_read)
    monkeypatch.setattr("pandas.ExcelFile", unexpected_read)
    source = FileSource(path)
    service = make_service(tmp_path)
    for action in (
        lambda: source.fetch(QuerySource(connection="file", query="data")),
        lambda: describe_source(source),
        lambda: service.upload_data(service.new_session(), path),
    ):
        with pytest.raises(ValueError, match="Expanded Office archive"):
            action()
    assert not service.sources
    assert not (service.onboarding.store.root / "sources").exists()


def test_public_tool_errors_do_not_echo_paths_urls_or_database_details(tmp_path):
    import httpx
    from sqlalchemy.exc import OperationalError

    secret = "private-token-and-database-user"
    request = httpx.Request("GET", f"https://internal.invalid/data?token={secret}")
    response = httpx.Response(403, request=request)
    errors = [
        FileNotFoundError(2, "missing", f"/private/{secret}/file"),
        OperationalError(f"SELECT '{secret}'", {"password": secret}, Exception(secret)),
        httpx.HTTPStatusError(str(request.url), request=request, response=response),
        ValueError(secret),
        KeyError(secret),
        RuntimeError(secret),
    ]
    service = make_service(tmp_path)

    class FailingSource:
        def fetch(self, source):
            raise current_error

    session = Onboarding()
    tools = {
        t.name: t
        for t in build_tools(session, service.onboarding, {"source": FailingSource()})
    }
    for current_error in errors:
        session.begin_turn()
        result = tools["preview_data"].invoke(
            {"connection": "source", "query": "data", "params": {}}
        )
        assert result == public_tool_error(current_error)
        serialized = json.dumps(result)
        assert secret not in serialized
        assert "internal.invalid" not in serialized
        assert "/private/" not in serialized
        assert result["error"] and result["kind"]


def test_validation_errors_keep_schema_fields_without_input_context_or_map_keys():
    secret = "privateCredential"
    with pytest.raises(ValidationError) as caught:
        ReportDefinition.model_validate(
            {
                "id": "test",
                "name": "Test",
                "layout": {"title": "Test", "blocks": []},
                "queries": {
                    secret: {
                        "connection": "source",
                        "query": "data",
                        "row_limit": secret,
                    }
                },
            }
        )
    result = public_tool_error(caught.value)
    assert secret not in json.dumps(result)
    assert any("row_limit" in issue["field"] for issue in result["issues"])
    assert "input" not in json.dumps(result)
    assert "ctx" not in json.dumps(result)


def test_preview_diagnostics_do_not_forward_renderer_exception_text(
    tmp_path, monkeypatch
):
    service = make_service(tmp_path)
    monkeypatch.setattr(
        service.onboarding,
        "preview",
        lambda *args: {
            "success": False,
            "diagnostics": [
                {
                    "stage": "render",
                    "code": "internal_error",
                    "message": "/secret/token",
                    "path": "/secret",
                }
            ],
        },
    )
    preview = next(
        t
        for t in build_tools(Onboarding(), service.onboarding, {})
        if t.name == "preview_report"
    )
    result = preview.invoke({"reference": "drafts/test", "parameters": {}})
    assert result == {
        "success": False,
        "diagnostics": [{"stage": "render", "code": "internal_error"}],
    }


def test_new_catalog_preset_renders_its_own_demo_rows(tmp_path, monkeypatch):
    import report_agent.agent.catalog as catalog

    preset = ReportTemplate(
        "new_preset",
        "New design",
        "New report",
        ("Summary", "Data"),
        "#123456",
        ({"Custom metric": "Illustrative result"},),
    )
    monkeypatch.setattr(catalog, "TEMPLATES", (preset,))
    assert catalog_context()[0]["demo_rows"] == preset.demo_rows
    service = make_service(tmp_path)
    captured = []
    monkeypatch.setattr(
        service.onboarding,
        "preview",
        lambda *args: captured.append(args) or {"success": True},
    )
    tool = next(
        t
        for t in build_tools(Onboarding(), service.onboarding, {})
        if t.name == "rendered_examples"
    )
    result = tool.invoke({"output_format": "pdf", "topic": "Custom report"})
    assert result[0]["success"] is True
    assert captured[0][3] == {"section_1": preset.demo_rows}
    definition = service.onboarding.store.load(captured[0][1])
    assert definition.queries["section_1"].columns == ["Custom metric"]


def test_harness_global_policy_registered_once_per_model(monkeypatch):
    import report_agent.agent.factory as factory

    calls = []
    monkeypatch.setattr(factory, "_REGISTERED_MODELS", set())
    monkeypatch.setattr(
        factory, "register_harness_profile", lambda *args: calls.append(args)
    )
    factory.initialize_harness("test-policy-once")
    factory.initialize_harness("test-policy-once")
    assert len(calls) == 1
    assert calls[0][0] == "openai:test-policy-once"
    assert "task" in calls[0][1].excluded_tools
    assert not calls[0][1].general_purpose_subagent.enabled
