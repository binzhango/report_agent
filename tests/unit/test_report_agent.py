"""Exercise real Deep Agents skill loading with a deterministic model transport."""

from pathlib import Path

import pytest

pytest.importorskip("deepagents")

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from report_agent.agent.config import AgentConfig
from report_agent.agent.factory import create_report_agent
from report_agent.application.conversation import ConversationService
from report_agent.application.onboarding import Onboarding, OnboardingService
from report_agent.application.report_runs import ReportRuns
from report_agent.interfaces.gradio.app import create_app
from report_agent.storage.report_definitions import ReportStore

ROOT = Path(__file__).resolve().parents[2]


def test_framework_loads_skills_and_keeps_history(monkeypatch, tmp_path):
    captured = []
    bound_tools = []
    responses = iter(
        [
            AIMessage(
                content="",
                tool_calls=[{"id": "context", "name": "report_context", "args": {}}],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "skill",
                        "name": "read_file",
                        "args": {"file_path": "/report-discovery/SKILL.md"},
                    }
                ],
            ),
            AIMessage(content="What should the report help someone decide?"),
            AIMessage(content="We can build a monthly sales report."),
        ]
    )

    def generate(self, messages, **kwargs):
        captured.append(messages)
        bound_tools.extend(t["function"]["name"] for t in kwargs.get("tools", []))
        return ChatResult(generations=[ChatGeneration(message=next(responses))])

    monkeypatch.setattr(ChatOpenAI, "_generate", generate)
    store = ReportStore(tmp_path / "library")
    onboarding = OnboardingService(store, ReportRuns(store, {}, tmp_path / "output"))
    session = Onboarding()
    config = AgentConfig("test-report-model", ROOT / ".agents/skills")
    graph = create_report_agent(
        config,
        session,
        onboarding,
        {},
        model=ChatOpenAI(
            model=config.model,
            api_key="offline-test",
            use_responses_api=False,
        ),
    )
    tool_names = set(graph.nodes["tools"].bound.tools_by_name)
    assert {"read_file", "create_draft", "propose_report_run"} <= tool_names
    assert not {"execute", "task", "write_file", "edit_file"} & tool_names
    invoke_config = {"configurable": {"thread_id": session.id}}
    first = graph.invoke(
        {
            "messages": [
                {"role": "user", "content": "I do not know what report I need."}
            ]
        },
        invoke_config,
    )
    assert first["messages"][-1].content.startswith("What should")
    state = graph.get_state(invoke_config).values
    assert "report-discovery" in str(state["skills_metadata"])
    assert any("Start with the decision" in str(m.content) for m in first["messages"])
    second = graph.invoke(
        {"messages": [{"role": "user", "content": "Monthly sales."}]}, invoke_config
    )
    assert len(second["messages"]) > len(first["messages"])
    assert any(m.content == "Monthly sales." for m in captured[-1])
    assert "report_context" in bound_tools
    assert not {"task", "execute", "write_file", "edit_file"} & set(bound_tools)


def test_frontend_builds_without_model_call_and_sessions_are_separate(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GRADIO_ANALYTICS_ENABLED", "False")
    config = AgentConfig("test-model", ROOT / ".agents/skills")
    store = ReportStore(tmp_path / "library")
    service = ConversationService(
        config, OnboardingService(store, ReportRuns(store, {}, tmp_path / "output")), {}
    )
    first, second = service.new_session(), service.new_session()
    service.sessions[first].pending = {"reference": "example", "parameters": {}}
    assert service.sessions[second].pending is None
    assert not service.agents
    app = create_app(service)
    labels = [
        component.get("props", {}).get("value")
        for component in app.get_config_file()["components"]
        if component["type"] == "button"
    ]
    assert "Send" in labels
    assert len(app.renderables) == 1  # Artifact actions are rendered inside the thread.
    service.remove_session(first)
    assert first not in service.sessions and second in service.sessions


def test_ui_failure_restores_controls_and_explains_context_limit(tmp_path):
    config = AgentConfig("test-model", ROOT / ".agents/skills")
    store = ReportStore(tmp_path / "library")
    service = ConversationService(
        config, OnboardingService(store, ReportRuns(store, {}, tmp_path / "runs")), {}
    )

    class FailingAgent:
        def invoke(self, *args, **kwargs):
            raise ValueError("context length exceeded; private-provider-detail")

    service.agent_factory = lambda *args: FailingAgent()
    app = create_app(service)
    chat = next(fn.fn for fn in app.fns.values() if fn.api_name == "chat")
    updates = list(chat("Help me create a report", None))
    assert updates[0][1][0]["content"] == "Help me create a report"
    assert updates[0][3]["interactive"] is False
    assert updates[-1][3]["interactive"] is True
    assert not any(e.get("active") for e in updates[-1][1])
    assert "32768" in updates[-1][2]
    assert "private-provider-detail" not in updates[-1][2]


def test_ui_acceptance_is_enabled_only_for_current_preview(tmp_path):
    config = AgentConfig("test-model", ROOT / ".agents/skills")
    store = ReportStore(tmp_path / "library")
    service = ConversationService(
        config, OnboardingService(store, ReportRuns(store, {}, tmp_path / "runs")), {}
    )
    key = service.new_session()
    session = service.sessions[key]
    session.draft = "drafts/current"
    session.preview_reference = "drafts/previous"
    session.preview_path = tmp_path / "preview.docx"
    session.files = [str(session.preview_path)]
    app = create_app(service)
    chat = next(fn.fn for fn in app.fns.values() if fn.api_name == "chat")
    assert not any(e.get("active") for e in list(chat("", key))[-1][1])
    session.preview_reference = session.draft
    session.preview_path = tmp_path / "current.docx"
    session.files = [str(session.preview_path)]
    assert any(e.get("active") for e in list(chat("", key))[-1][1])
    session.pending = {
        "reference": "accepted/example/v1",
        "parameters": {"month": "November"},
    }
    result = list(chat("", key))[-1]
    card = next(e for e in result[1] if e["kind"] == "parameters")
    assert card["active"] is True
    assert card["proposal"]["parameters"] == {"month": "November"}


def test_empty_model_answer_is_not_reported_as_success(tmp_path):
    from report_agent.application.conversation import EmptyModelResponse

    config = AgentConfig("test-model", ROOT / ".agents/skills")
    store = ReportStore(tmp_path / "library")

    class EmptyAgent:
        def invoke(self, *args, **kwargs):
            return {"messages": [AIMessage(content="")]}

    service = ConversationService(
        config,
        OnboardingService(store, ReportRuns(store, {}, tmp_path / "runs")),
        {},
        agent_factory=lambda *args: EmptyAgent(),
    )
    key = service.new_session()
    with pytest.raises(EmptyModelResponse):
        service.send(key, "Create a report")
    assert service.sessions[key].history == [
        {"role": "user", "content": "Create a report"}
    ]


def test_resumed_draft_requires_a_new_preview_before_acceptance(tmp_path):
    from report_agent.agent.tools.reports import build_tools
    from report_agent.definitions.models import ReportDefinition

    store = ReportStore(tmp_path / "library")
    definition = ReportDefinition.model_validate(
        {
            "id": "resumable",
            "name": "Resumable report",
            "layout": {
                "title": "Review",
                "blocks": [{"name": "intro", "text": "Fixed text."}],
            },
        }
    )
    reference = store.draft(definition)
    assert store.list_drafts()[0]["reference"] == reference
    latest = store.draft(definition)
    assert [item["reference"] for item in store.list_drafts()] == [latest]
    onboarding = OnboardingService(store, ReportRuns(store, {}, tmp_path / "runs"))
    session = Onboarding(preview_reference="previous", preview_path=tmp_path / "old")
    resume = next(
        t
        for t in build_tools(session, onboarding, {})
        if t.name == "resume_report_draft"
    )
    assert resume.invoke({"reference": reference})["name"] == "Resumable report"
    assert session.draft == reference
    assert session.preview_reference is None and session.preview_path is None
    with pytest.raises(ValueError, match="Preview"):
        onboarding.accept(session)


def test_uploads_are_immediate_and_do_not_require_a_model(tmp_path):
    config = AgentConfig("unreachable-model", ROOT / ".agents/skills")
    store = ReportStore(tmp_path / "library")
    service = ConversationService(
        config, OnboardingService(store, ReportRuns(store, {}, tmp_path / "runs")), {}
    )
    app = create_app(service)
    key = service.new_session()
    sample = next(fn.fn for fn in app.fns.values() if fn.api_name == "upload_sample")
    data = next(fn.fn for fn in app.fns.values() if fn.api_name == "upload_data")
    list(sample(str(ROOT / "examples/conversations/sales-example.docx"), key))
    assert service.sessions[key].sample["format"] == "docx"
    service.sessions[key].pending = {"reference": "old", "parameters": {}}
    result = list(data(str(ROOT / "examples/conversations/milestones.xlsx"), key))[-1]
    assert any("milestone" in e.get("content", "") for e in result[1])
    assert service.sessions[key].pending is None
    assert not service.agents


def test_fenced_sql_is_shown_only_when_requested_without_removing_prose(tmp_path):
    config = AgentConfig("test-model", ROOT / ".agents/skills")
    store = ReportStore(tmp_path / "library")

    class Agent:
        def invoke(self, *args, **kwargs):
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "Report preview is ready.\n"
                            "Select the region you want from your workbook.\n"
                            "```sql\nSELECT revenue FROM sales\n```\n"
                            "Please review the report."
                        )
                    )
                ]
            }

    service = ConversationService(
        config,
        OnboardingService(store, ReportRuns(store, {}, tmp_path / "runs")),
        {},
        agent_factory=lambda *args: Agent(),
    )
    key = service.new_session()
    service.send(key, "Build my report")
    assert "SELECT" not in service.sessions[key].history[-1]["content"]
    assert (
        "Select the region you want from your workbook."
        in (service.sessions[key].history[-1]["content"])
    )
    assert "Please review" in service.sessions[key].history[-1]["content"]
    service.send(key, "Show the SQL")
    assert "SELECT revenue FROM sales" in service.sessions[key].history[-1]["content"]


def test_tool_artifact_is_sent_to_chat_before_the_final_answer(tmp_path):
    from report_agent.definitions.models import ReportDefinition

    store = ReportStore(tmp_path / "library")
    draft = store.draft(
        ReportDefinition.model_validate(
            {
                "id": "live_preview",
                "name": "Live preview",
                "layout": {"title": "Live preview", "blocks": [{"name": "intro"}]},
            }
        )
    )
    output = tmp_path / "preview.pdf"
    output.write_bytes(b"preview fixture")

    def factory(settings, session, onboarding, sources):
        class Agent:
            def invoke(self, request, config):
                session.draft = session.preview_reference = draft
                session.preview_path = output
                session.files = [str(output)]
                config["callbacks"][0].on_tool_end({})
                return {"messages": [AIMessage(content="Your preview is ready.")]}

        return Agent()

    service = ConversationService(
        AgentConfig("offline", ROOT / ".agents/skills"),
        OnboardingService(store, ReportRuns(store, {}, tmp_path / "runs")),
        {},
        agent_factory=factory,
    )
    app = create_app(service)
    chat = next(fn.fn for fn in app.fns.values() if fn.api_name == "chat")
    updates = list(chat("Preview my report", None))
    live = next(u for u in updates[:-1] if any(e["kind"] == "report" for e in u[1]))
    assert live[3]["interactive"] is False
    assert not any(e.get("content") == "Your preview is ready." for e in live[1])
    assert not next(e for e in live[1] if e["kind"] == "report")["active"]
    final = updates[-1][1]
    assert next(e for e in final if e["kind"] == "report")["active"]
    assert sum(e["kind"] == "report" for e in final) == 1
