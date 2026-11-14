"""Application controls remain effective when a model ignores its instructions."""

from concurrent.futures import ThreadPoolExecutor

import pytest

pytest.importorskip("deepagents")

from langchain_core.messages import AIMessage

from report_agent.agent.config import AgentConfig
from report_agent.agent.tools.reports import build_tools
from report_agent.application.conversation import ConversationService
from report_agent.application.onboarding import OnboardingService
from report_agent.application.report_runs import ReportRuns
from report_agent.definitions.models import ReportDefinition
from report_agent.errors import ReportError
from report_agent.interfaces.gradio.transcript import snapshot
from report_agent.models.results import RenderResult
from report_agent.storage.report_definitions import ReportStore


def definition():
    return ReportDefinition.model_validate(
        {
            "id": "sales",
            "name": "Sales",
            "layout": {"title": "Sales", "blocks": [{"name": "rows", "kind": "table"}]},
            "queries": {
                "rows": {
                    "connection": "db",
                    "query": "SELECT amount FROM sales "
                    "WHERE day >= :start AND day < :end",
                    "parameter_bindings": {"start": "start_date", "end": "end_date"},
                }
            },
            "parameters": {
                "start_date": {"type": "date"},
                "end_date": {"type": "date"},
            },
            "parameter_order": [{"before": "start_date", "after": "end_date"}],
        }
    )


@pytest.fixture
def service(tmp_path):
    store = ReportStore(tmp_path / "library")
    onboarding = OnboardingService(store, ReportRuns(store, {}, tmp_path / "runs"))
    return ConversationService(
        AgentConfig("offline", tmp_path),
        onboarding,
        {},
        agent_factory=lambda *args: None,
    )


def tools_for(service, session):
    return {
        t.name: t for t in build_tools(session, service.onboarding, service.sources)
    }


def test_proposal_errors_are_distinct_and_actionable(service, tmp_path):
    session = service.get_session(service.new_session())
    draft = service.onboarding.store.draft(definition())
    preview = tmp_path / "fixture.docx"
    preview.write_bytes(b"fixture")
    accepted = service.onboarding.store.accept(draft, preview)
    propose = tools_for(service, session)["propose_report_run"]
    cases = [
        (draft, {}, "acceptance_required", "Accept the template"),
        (
            accepted,
            {"start_date": "2026-11-01", "end_date": "2026-10-01"},
            "parameter_order",
            "start_date must be before end_date",
        ),
        ("accepted/../../secret", {}, "invalid_reference", "Invalid report reference"),
        ("../../secret", {}, "invalid_reference", "Invalid report reference"),
        (
            accepted,
            {"start_date": "private-token", "end_date": "2026-10-01"},
            "invalid_date",
            "YYYY-MM-DD",
        ),
    ]
    for reference, params, code, message in cases:
        session.begin_turn()
        result = propose.invoke({"reference": reference, "parameters": params})
        assert result["code"] == code
        assert message in result["error"]
        assert "private-token" not in str(result)
        assert "secret" not in str(result)


def test_repairs_are_capped_even_with_parallel_tool_calls_and_reset_on_message(service):
    session = service.get_session(service.new_session())
    calls = []

    class Source:
        def fetch(self, query):
            calls.append(query)
            raise ReportError("Fix the selected columns.", code="columns_required")

    service.sources["source"] = Source()
    preview = tools_for(service, session)["preview_data"]
    args = {"connection": "source", "query": "data", "params": {}}
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: preview.invoke(args), range(6)))
    assert len(calls) == 3  # Initial attempt plus two repairs.
    assert sum(r.get("code") == "repair_limit" for r in results) == 3
    assert session.repair_attempts == 2

    class Agent:
        def invoke(self, *request_args, **kwargs):
            assert session.repair_attempts == 0
            assert not session.repair_pending
            result = preview.invoke(args)
            assert result["code"] == "columns_required"
            return {"messages": [AIMessage(content="Please confirm the column.")]}

    service.agent_factory = lambda *args: Agent()
    service.send(session.id, "Use another column")
    assert len(calls) == 4


def test_real_bindings_cannot_be_replaced_with_synthetic_rows(service, monkeypatch):
    session = service.get_session(service.new_session())
    draft = service.onboarding.stage(session, definition().model_dump())
    monkeypatch.setattr(
        service.onboarding.runs,
        "run",
        lambda *args, **kwargs: pytest.fail("Synthetic substitution reached renderer"),
    )
    result = tools_for(service, session)["preview_report"].invoke(
        {
            "reference": draft,
            "parameters": {},
            "sample_tables": {"rows": [{"amount": 999}]},
        }
    )
    assert result["code"] == "demo_substitution_blocked"
    assert session.preview_reference is None


def test_query_review_is_bound_to_the_rendered_draft(service, tmp_path, monkeypatch):
    session = service.get_session(service.new_session())
    draft = service.onboarding.stage(session, definition().model_dump())
    preview = tmp_path / "preview.docx"
    preview.write_bytes(b"fixture")
    monkeypatch.setattr(
        service.onboarding.runs,
        "run",
        lambda *args, **kwargs: RenderResult(output_path=preview),
    )
    monkeypatch.setattr(
        "report_agent.application.onboarding.thumbnails", lambda result: []
    )
    service.onboarding.preview(
        session, draft, {"start_date": "2026-10-01", "end_date": "2026-11-01"}
    )
    card = snapshot(session)[0]
    assert (
        card["query_review"]["queries"]["rows"]["query"]
        == definition().queries["rows"].query
    )
    assert card["query_review"]["parameters"]["start_date"] == "2026-10-01"
    with pytest.raises(ReportError, match="Review the queries"):
        service.onboarding.accept(session)
    accepted = service.onboarding.accept(session, queries_reviewed=True)
    assert accepted.startswith("accepted/")
    saved = next(e for e in snapshot(session) if e["kind"] == "report")
    assert saved["accepted"]["reference"] == accepted
    assert saved["accepted"]["queries_reviewed"] is True
    assert not saved["active"]
    service.onboarding.stage(session, definition().model_dump())
    assert (
        next(e for e in snapshot(session) if e["kind"] == "report")["accepted"][
            "reference"
        ]
        == accepted
    )
    assert not session.preview_queries
    with pytest.raises(ReportError, match="Preview the current"):
        service.onboarding.accept(session, queries_reviewed=True)


def test_example_drafts_are_cleaned_without_deleting_other_sessions_or_user_drafts(
    service, monkeypatch
):
    first = service.get_session(service.new_session())
    second = service.get_session(service.new_session())
    store = service.onboarding.store
    user_draft = store.draft(definition())
    monkeypatch.setattr(service.onboarding, "preview", lambda *args: {"success": True})
    tools = tools_for(service, first)

    def generate():
        return tools["rendered_examples"].invoke(
            {"output_format": "docx", "topic": "Demo"}
        )

    generate()
    old = first.example_drafts.copy()
    assert len(old) == 3
    generate()
    assert not any((store.root / ref).exists() for ref in old)
    chosen = next(iter(first.example_drafts))
    tools["resume_report_draft"].invoke({"reference": chosen})
    assert first.example_drafts == {chosen}
    assert store.path(chosen).is_dir()
    generate()
    assert first.draft is None
    assert not (store.root / chosen).exists()
    owned = first.example_drafts.copy()
    tools_for(service, second)["rendered_examples"].invoke(
        {"output_format": "docx", "topic": "Other"}
    )
    other = second.example_drafts.copy()
    service.remove_session(first.id)
    assert not any((store.root / ref).exists() for ref in owned)
    assert all(store.path(ref).is_dir() for ref in other)
    assert store.path(user_draft).is_dir()
    service.onboarding.stage(second, definition().model_dump())
    assert not second.example_drafts
    assert not any((store.root / ref).exists() for ref in other)
    with pytest.raises(ReportError):
        store.delete_draft("accepted/sales/v1")
