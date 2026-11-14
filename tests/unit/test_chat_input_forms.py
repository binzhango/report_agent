"""Interactive questions round-trip through real agent tools and session state."""

from pathlib import Path

import pytest

pytest.importorskip("deepagents")

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from report_agent.agent.config import AgentConfig
from report_agent.agent.factory import create_report_agent
from report_agent.agent.tools.reports import build_tools
from report_agent.application.conversation import ConversationService
from report_agent.application.input_forms import InputForm
from report_agent.application.onboarding import OnboardingService
from report_agent.application.report_runs import ReportRuns
from report_agent.definitions.models import ReportDefinition
from report_agent.errors import ReportError
from report_agent.interfaces.gradio.input_forms import unpack_answers
from report_agent.interfaces.gradio.transcript import snapshot
from report_agent.storage.report_definitions import ReportStore

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def service(tmp_path):
    store = ReportStore(tmp_path / "library")
    onboarding = OnboardingService(store, ReportRuns(store, {}, tmp_path / "runs"))
    return ConversationService(
        AgentConfig("offline", ROOT / ".agents/skills"),
        onboarding,
        {},
        agent_factory=lambda *args: None,
    )


def request_tool(service, session):
    return next(
        t
        for t in build_tools(session, service.onboarding, service.sources)
        if t.name == "request_report_inputs"
    )


def test_typed_questions_support_dates_months_other_and_open_answers():
    form = InputForm(
        title="Report details",
        fields=[
            {"id": "month", "label": "Reporting month", "type": "month"},
            {"id": "start", "label": "Start date", "type": "date"},
            {
                "id": "scope",
                "label": "Scope",
                "type": "select",
                "choices": ["All rows", "Project"],
                "allow_other": True,
            },
            {
                "id": "notes",
                "label": "What should this report explain?",
                "type": "multiline",
                "required": False,
            },
            {"id": "count", "label": "Count", "type": "integer"},
            {"id": "chart", "label": "Include chart", "type": "boolean"},
        ],
    )
    values = unpack_answers(
        form.model_dump()["fields"],
        [
            "November 2026",
            "2026-11-01",
            "Other…",
            "Department: Engineering",
            "Explain late milestones",
            3.0,
            "no",
        ],
    )
    assert form.validate_answers(values) == {
        "month": "2026-11",
        "start": "2026-11-01",
        "scope": "Department: Engineering",
        "notes": "Explain late milestones",
        "count": 3,
        "chart": False,
    }
    for name, bad in [
        ("month", "last someday"),
        ("start", "2026-02-30"),
        ("count", 1.2),
        ("chart", "maybe"),
        ("scope", ""),
    ]:
        with pytest.raises(ReportError):
            form.validate_answers({**values, name: bad})


def test_invalid_answers_do_not_consume_form_and_submitted_answers_are_immutable(
    service,
):
    session = service.get_session(service.new_session())
    request_tool(service, session).invoke(
        {
            "title": "Report details",
            "fields": [
                {
                    "id": "purpose",
                    "label": "What should it help you decide?",
                    "type": "multiline",
                }
            ],
        }
    )
    first = snapshot(session)[0]
    assert first["active"]
    form_id = session.input_form["id"]
    with pytest.raises(ReportError, match="enter a value"):
        service.submit_inputs(session.id, form_id, {"purpose": " "})
    assert session.input_form["id"] == form_id
    result = service.submit_inputs(
        session.id, form_id, {"purpose": "Plan the next release"}
    )
    assert (
        "Plan the next release" in result["message"] and result["report_run"] is False
    )
    answered = snapshot(session)[0]
    assert not answered["active"]
    assert answered["answers"] == {"purpose": "Plan the next release"}
    assert first.get("answers") is None
    with pytest.raises(ReportError, match="changed"):
        service.submit_inputs(session.id, form_id, {"purpose": "Duplicate submission"})


def test_replacing_or_sending_a_message_disables_previous_forms(service):
    session = service.get_session(service.new_session())
    tool = request_tool(service, session)
    args = {"title": "Question", "fields": [{"id": "audience", "label": "Audience"}]}
    tool.invoke(args)
    old_id = session.input_form["id"]
    snapshot(session)
    # New explicit turn can request replacement questions.
    session.input_form = None
    tool.invoke(args)
    assert [e["active"] for e in snapshot(session)] == [False, True]
    with pytest.raises(ReportError, match="changed"):
        service.submit_inputs(session.id, old_id, {"audience": "Managers"})

    class Agent:
        def invoke(self, *args, **kwargs):
            return {"messages": [AIMessage(content="We can change direction.")]}

    service.agent_factory = lambda *args: Agent()
    service.send(session.id, "Change the report topic instead")
    assert not any(e["active"] for e in snapshot(session) if e["kind"] == "input_form")


def test_saved_schema_form_validates_and_proposes_without_any_model_call(
    service, tmp_path
):
    definition = ReportDefinition.model_validate(
        {
            "id": "monthly",
            "name": "Monthly",
            "layout": {"title": "Monthly", "blocks": [{"name": "intro"}]},
            "parameters": {
                "start_date": {"type": "date"},
                "end_date": {"type": "date"},
                "count": {"type": "integer", "choices": [1, 2], "default": 1},
                "chart": {"type": "boolean", "default": False},
            },
            "parameter_order": [{"before": "start_date", "after": "end_date"}],
        }
    )
    store = service.onboarding.store
    draft = store.draft(definition)
    sample = tmp_path / "sample.docx"
    sample.write_bytes(b"fixture")
    accepted = store.accept(draft, sample)
    session = service.get_session(service.new_session())
    request_tool(service, session).invoke(
        {
            "title": "Monthly inputs",
            "report_reference": accepted,
            "known_parameters": {"start_date": "2026-11-01"},
        }
    )
    form = session.input_form
    assert [(f["id"], f["type"]) for f in form["fields"]] == [
        ("start_date", "date"),
        ("end_date", "date"),
        ("count", "select"),
        ("chart", "boolean"),
    ]
    with pytest.raises(ReportError, match="before"):
        service.submit_inputs(
            session.id,
            form["id"],
            {
                "start_date": "2026-11-01",
                "end_date": "2026-10-01",
                "count": "2",
                "chart": "no",
            },
        )
    result = service.submit_inputs(
        session.id,
        form["id"],
        {
            "start_date": "2026-11-01",
            "end_date": "2026-12-01",
            "count": "2",
            "chart": "no",
        },
    )
    assert result["report_run"] is True
    assert session.pending["parameters"] == {
        "start_date": "2026-11-01",
        "end_date": "2026-12-01",
        "count": 2,
        "chart": False,
    }
    assert not service.agents


def test_real_graph_pauses_for_a_form_and_repairs_invalid_form_requests(
    service, monkeypatch
):
    generated = []
    responses = iter(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "bad",
                        "name": "request_report_inputs",
                        "args": {
                            "title": "Details",
                            "fields": [
                                {"id": "audience", "label": "Audience"},
                                {"id": "audience", "label": "Audience again"},
                            ],
                        },
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "good",
                        "name": "request_report_inputs",
                        "args": {
                            "title": "Details",
                            "fields": [
                                {
                                    "id": "audience",
                                    "label": "Who will read it?",
                                    "type": "text",
                                }
                            ],
                        },
                    }
                ],
            ),
            AIMessage(content="The report will be written for department managers."),
        ]
    )

    def generate(self, messages, **kwargs):
        generated.append(messages)
        return ChatResult(generations=[ChatGeneration(message=next(responses))])

    monkeypatch.setattr(ChatOpenAI, "_generate", generate)
    model = ChatOpenAI(model="offline", api_key="offline", use_responses_api=False)
    service.agent_factory = lambda config, session, onboarding, sources: (
        create_report_agent(config, session, onboarding, sources, model=model)
    )
    key = service.new_session()
    session = service.send(key, "Help me make a report")
    assert (
        len(generated) == 2
    )  # Invalid form repaired; valid form waits without another model call.
    assert any(
        "Form field IDs must be unique" in str(m.content)
        for m in generated[1]
        if m.type == "tool"
    )
    assert session.repair_attempts == 1
    assert session.input_form["fields"][0]["id"] == "audience"
    result = service.submit_inputs(
        key, session.input_form["id"], {"audience": "Department managers"}
    )
    service.send(key, result["message"], display_message=result["summary"])
    assert len(generated) == 3
    assert any(
        "Department managers" in str(m.content)
        for m in generated[-1]
        if m.type == "human"
    )
    assert session.history[-2]["content"] == "Who will read it?: Department managers"
    assert session.input_form is None
